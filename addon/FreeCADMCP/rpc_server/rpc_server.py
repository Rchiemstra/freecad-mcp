import FreeCAD
import FreeCADGui
import ObjectsFem

import contextlib
import hashlib
import hmac
import ipaddress
import inspect
import json
import logging
import platform
import re
import base64
import io
import os
import sys
import tempfile
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from xmlrpc.client import Fault, dumps as xmlrpc_dumps, loads as xmlrpc_loads
from xmlrpc.server import SimpleXMLRPCRequestHandler, SimpleXMLRPCServer

from PySide import QtCore, QtWidgets

try:
    from document_state import (
        document_modified_or_dirty,
        require_document_modified,
    )
except ImportError:
    from addon.FreeCADMCP.document_state import (
        document_modified_or_dirty,
        require_document_modified,
    )

from .execution_safety import find_gui_blocking_risk, find_gui_geometry_loop_risk
from .gui_dispatcher import (
    GuiBusyAfterTimeout,
    GuiDispatchError,
    GuiDispatchTimeout,
    GuiDispatcher,
    GuiTaskError,
)
from .inflight_requests import (
    InflightLeaseCredential,
    InflightRequestRegistry,
    RequestCancellationError,
)
from .lease_protocol import (
    LeaseProtocolError,
    RequestReplayCache,
    SessionManager,
    load_profile_secret,
    make_runtime_manifest,
    public_error as lease_protocol_public_error,
    redact_sensitive as redact_lease_protocol_details,
)
from .mutation_guard import (
    GuiMutationTransaction,
    make_method_spec,
    validate_document_invariants,
)
from .parts_library import (
    configure_parts_library_path,
    get_parts_list,
    insert_part_from_library,
)
from .reference_repair import inspect_references_gui, repair_references_gui
from .serialize import serialize_object
from .settings import (
    DEFAULT_SETTINGS as _DEFAULT_SETTINGS,  # noqa: F401 - compatibility export
    SettingsPolicyError,
    get_settings_path as _get_settings_path,  # noqa: F401 - compatibility export
    load_settings,
    resolve_rpc_bind_host,
)
from .snapshot_service import (
    create_lease_baseline_snapshot_gui,
    create_primary_snapshot_gui,
    discard_lease_baseline_snapshot,
    recovery_snapshot_path,
    restore_snapshot_in_place_gui,
)
from .save_service import (
    SaveService,
    SaveServiceError,
    compare_file_to_baseline,
)
from .view_manager import (
    animate_object_placement,
    build_orbit_frames,
    repair_placements_and_refresh,
    refresh_active_view,
    save_active_screenshot,
    save_view_sequence,
)
from .worker_manager import WorkerManager, WorkerRuntime
from .fem_executor import run_fem_analysis as _run_fem_analysis

rpc_server_thread = None
rpc_server_instance = None
gui_dispatcher = None
worker_manager = None
snapshot_coordinator = threading.Lock()


def _generated_execute_signature(
    *,
    session_token,
    request_id,
    code,
    options,
):
    affected = options.get("affected_documents") or ()
    payload = {
        "request_id": str(request_id or ""),
        "operation_id": str(options.get("operation_id") or ""),
        "code_sha256": hashlib.sha256(str(code).encode("utf-8")).hexdigest(),
        "document": str(options.get("document") or ""),
        "affected_documents": sorted({str(item) for item in affected}),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hmac.new(str(session_token).encode("utf-8"), canonical, hashlib.sha256)
    return f"hmac-sha256:{digest.hexdigest()}"


def _validate_generated_operation_envelope(envelope):
    """Authenticate session-derived execute metadata before replay lookup.

    The signature rotates with the RPC session and is intentionally omitted
    from the semantic request fingerprint.  Omitting it is safe only after the
    current envelope has independently proved the capability.
    """

    if envelope.method != "execute_code":
        return
    options = envelope.params.get("options")
    if not isinstance(options, dict) or not options.get("generated_operation"):
        return
    code = envelope.params.get("code")
    operation_id = str(options.get("operation_id") or "")
    supplied = str(options.get("operation_signature") or "")
    if not isinstance(code, str) or not operation_id or not supplied:
        raise LeaseProtocolError(
            "GENERATED_OPERATION_SIGNATURE_INVALID",
            "The generated-operation capability signature is missing or invalid",
        )
    expected = _generated_execute_signature(
        session_token=envelope.session_token,
        request_id=envelope.request_id,
        code=code,
        options=options,
    )
    if not hmac.compare_digest(supplied, expected):
        raise LeaseProtocolError(
            "GENERATED_OPERATION_SIGNATURE_INVALID",
            "The generated-operation capability signature is missing or invalid",
        )


shutdown_requested = threading.Event()
logger = logging.getLogger("FreeCADMCP.rpc_server")
addon_loaded_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
# One runtime identity belongs to the FreeCAD/addon process, not to a listener
# restart.  Restarting XML-RPC issues new authenticated sessions but must not
# impersonate a different FreeCAD runtime in sidecars or instance manifests.
_ADDON_RUNTIME_ID = str(uuid.uuid4())
rpc_server_runtime_id = _ADDON_RUNTIME_ID
rpc_server_started_at = ""
rpc_server_actual_endpoint = None
rpc_session_manager = None
# Request-id authority belongs to the addon process, not to one listener or
# one short-lived authenticated session.  Listener Stop/Start must retain it.
rpc_request_replay_cache = RequestReplayCache()
# Process-wide by design: handler timeouts and listener shutdown must not erase
# the ownership/cancellation state of GUI work that is still completing.
rpc_inflight_request_registry = InflightRequestRegistry()
document_identity_service = None
document_lease_service = None
document_lease_runtime_policy = None
document_lease_runtime_mode = None
rpc_runtime_manifest = None
save_service = None
lease_watchdog_thread = None
lease_watchdog_stop = threading.Event()
lease_watchdog_lock = threading.RLock()
RPC_SHUTDOWN_CANCELLATION_WAIT_SECONDS = 0.5


def _lease_watchdog_loop(interval_seconds=2.0, stop_event=None):
    """Fence expired leases even when the owning MCP process has disappeared."""

    stop_event = stop_event or lease_watchdog_stop
    while not stop_event.wait(float(interval_seconds)):
        service = document_lease_service
        if service is None:
            continue
        try:
            expired = service.mark_expired_stale()
        except Exception:
            logger.exception("Document lease watchdog failed")
            continue
        if not expired:
            continue
        logger.warning("Marked expired document leases stale: %s", ", ".join(expired))
        try:
            from lock_indicator import refresh_lock_indicator

            # The indicator owns the Qt queued-signal hop; this thread never
            # accesses a widget directly.
            refresh_lock_indicator()
        except Exception:
            logger.debug("Could not queue lease indicator refresh", exc_info=True)


def _ensure_lease_watchdog_running(interval_seconds=2.0):
    """Start exactly one process-lifetime stale-expiry daemon."""

    global lease_watchdog_thread, lease_watchdog_stop
    with lease_watchdog_lock:
        current = lease_watchdog_thread
        if current is not None and current.is_alive():
            return current
        stop_event = threading.Event()
        thread = threading.Thread(
            target=_lease_watchdog_loop,
            args=(float(interval_seconds), stop_event),
            name="FreeCADMCP-LeaseWatchdog",
            daemon=True,
        )
        lease_watchdog_stop = stop_event
        lease_watchdog_thread = thread
        thread.start()
        return thread


def shutdown_document_lease_runtime(timeout=3.0):
    """Stop only the process-lifetime daemon during final addon teardown/tests.

    Lease/identity services and every active or foreign recovery record remain
    intact. Listener stop/restart must never call this helper.
    """

    global lease_watchdog_thread
    with lease_watchdog_lock:
        thread = lease_watchdog_thread
        stop_event = lease_watchdog_stop
        if thread is None:
            return True
        stop_event.set()
    if thread is not threading.current_thread():
        thread.join(timeout=max(0.0, float(timeout)))
    with lease_watchdog_lock:
        if lease_watchdog_thread is thread and not thread.is_alive():
            lease_watchdog_thread = None
        return lease_watchdog_thread is None


def initialize_document_lease_runtime(settings=None):
    """Create process-lifetime document identity/lease authority.

    The runtime is intentionally independent from the XML-RPC listener.  This
    lets observers and the status UI detect foreign sidecars before auto-start
    and preserves document session UUIDs across listener restarts.
    """

    global document_identity_service, document_lease_service
    global document_lease_runtime_policy, document_lease_runtime_mode, save_service
    global rpc_request_replay_cache

    settings = dict(settings or load_settings())
    lease_mode = str(settings.get("document_lease_mode") or "off")
    if lease_mode not in {"off", "observe", "enforce"}:
        raise SettingsPolicyError(
            "document_lease_mode must be one of: enforce, observe, off"
        )
    persist_task_summary = settings.get("persist_task_summary_in_sidecar", False)
    if not isinstance(persist_task_summary, bool):
        raise SettingsPolicyError(
            "persist_task_summary_in_sidecar must be true or false"
        )
    desired_policy = (
        lease_mode == "enforce",
        bool(settings.get("allow_network_sidecar", False)),
        persist_task_summary,
    )
    lease = _import_document_lease()

    if document_identity_service is None:
        document_identity_service = lease.DocumentIdentityService()
    effective_records = (
        getattr(
            document_lease_service,
            "list_effective_records",
            document_lease_service.list_records,
        )()
        if document_lease_service is not None
        else []
    )
    if (
        document_lease_runtime_mode is not None
        and document_lease_runtime_mode != lease_mode
        and effective_records
    ):
        raise SettingsPolicyError(
            "document lease mode cannot change while active lease or recovery "
            "records exist"
        )
    if (
        document_lease_service is not None
        and document_lease_runtime_policy != desired_policy
    ):
        if effective_records:
            raise SettingsPolicyError(
                "document lease sidecar policy cannot change while active "
                "lease or recovery records exist"
            )
        document_lease_service = None
    if document_lease_service is None:
        document_lease_service = lease.DocumentLeaseService(
            document_identity_service,
            lease.SidecarStore(
                strict_permissions=desired_policy[0],
                allow_network=desired_policy[1],
                persist_task_summary=desired_policy[2],
            ),
            local_runtime_identity=_make_local_runtime_identity(settings, lease),
            process_liveness_probe=_probe_process_liveness,
        )
        document_lease_runtime_policy = desired_policy
    document_lease_runtime_mode = lease_mode
    _import_document_lock().configure_runtime_lease_mode(lease_mode)
    if rpc_request_replay_cache is None:
        # Compatibility for tests or an older module state hot-reloaded into
        # this FreeCAD process.  Ordinary listener restarts reuse the object.
        rpc_request_replay_cache = RequestReplayCache()
    rpc_request_replay_cache.set_owner_lease_predicate(
        document_lease_service.has_unresolved_owner
    )
    if save_service is None:
        save_service = SaveService(platform=document_identity_service.platform)

    try:
        for document in FreeCAD.listDocuments().values():
            _ensure_v2_document(document)
    except Exception as exc:
        logger.warning("Could not register all live document identities: %s", exc)
    _ensure_lease_watchdog_running()
    return document_lease_service


def _utc_timestamp(value):
    return (
        datetime.fromtimestamp(value, timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _process_started_at():
    """Return the current process start time without requiring psutil."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            create = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel = wintypes.FILETIME()
            user = wintypes.FILETIME()
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.kernel32.GetProcessTimes(
                handle,
                ctypes.byref(create),
                ctypes.byref(exit_time),
                ctypes.byref(kernel),
                ctypes.byref(user),
            ):
                ticks = (int(create.dwHighDateTime) << 32) | int(create.dwLowDateTime)
                return _utc_timestamp(ticks / 10_000_000 - 11_644_473_600)
        except Exception:
            pass
    try:
        stat_fields = Path("/proc/self/stat").read_text(encoding="ascii").split()
        boot_seconds = float(
            next(
                line.split()[1]
                for line in Path("/proc/stat").read_text(encoding="ascii").splitlines()
                if line.startswith("btime ")
            )
        )
        return _utc_timestamp(
            boot_seconds + float(stat_fields[21]) / float(os.sysconf("SC_CLK_TCK"))
        )
    except Exception:
        return addon_loaded_at


def _boot_identity():
    """Compatibility accessor for the one trusted process-lifetime boot ID."""

    return _trusted_boot_identity()


def _trusted_boot_identity():
    """Return OS boot evidence, or empty text when it cannot be proven."""

    try:
        value = (
            Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
        )
        if value:
            return value
    except (OSError, UnicodeError):
        pass
    if os.name == "nt":
        try:
            import ctypes

            buffer = (ctypes.c_ubyte * 64)()
            returned = ctypes.c_ulong()
            status = ctypes.windll.ntdll.NtQuerySystemInformation(
                3, buffer, ctypes.sizeof(buffer), ctypes.byref(returned)
            )
            if status == 0:
                boot_ticks = ctypes.c_int64.from_buffer(buffer).value
                if boot_ticks > 0:
                    return f"windows-boot:{boot_ticks:x}"
        except Exception:
            pass
    try:
        import psutil

        boot_time = float(psutil.boot_time())
        if boot_time > 0:
            return f"boot-time:{boot_time:.6f}"
    except Exception:
        pass
    return ""


def _probe_process_liveness(pid):
    """Return exact process-start evidence, never guessing through errors."""

    lease = _import_document_lease()
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return lease.ProcessLivenessEvidence(exists=None)
    if pid < 1:
        return lease.ProcessLivenessEvidence(exists=None)

    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = [
                wintypes.DWORD,
                wintypes.BOOL,
                wintypes.DWORD,
            ]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.GetProcessTimes.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME),
            ]
            kernel32.GetProcessTimes.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                # ERROR_INVALID_PARAMETER is Windows' documented result for a
                # PID that does not identify a process. Access denial and all
                # other failures remain unknown.
                if ctypes.get_last_error() == 87:
                    return lease.ProcessLivenessEvidence(exists=False)
                return lease.ProcessLivenessEvidence(exists=None)
            try:
                create = wintypes.FILETIME()
                exit_time = wintypes.FILETIME()
                kernel = wintypes.FILETIME()
                user = wintypes.FILETIME()
                if not kernel32.GetProcessTimes(
                    handle,
                    ctypes.byref(create),
                    ctypes.byref(exit_time),
                    ctypes.byref(kernel),
                    ctypes.byref(user),
                ):
                    return lease.ProcessLivenessEvidence(exists=None)
                ticks = (int(create.dwHighDateTime) << 32) | int(create.dwLowDateTime)
                return lease.ProcessLivenessEvidence(
                    exists=True,
                    process_started_at=_utc_timestamp(
                        ticks / 10_000_000 - 11_644_473_600
                    ),
                )
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return lease.ProcessLivenessEvidence(exists=None)

    if sys.platform.startswith("linux"):
        try:
            raw = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
            fields = raw[raw.rfind(")") + 2 :].split()
            start_ticks = float(fields[19])
            boot_seconds = float(
                next(
                    line.split()[1]
                    for line in Path("/proc/stat")
                    .read_text(encoding="ascii")
                    .splitlines()
                    if line.startswith("btime ")
                )
            )
            return lease.ProcessLivenessEvidence(
                exists=True,
                process_started_at=_utc_timestamp(
                    boot_seconds + start_ticks / float(os.sysconf("SC_CLK_TCK"))
                ),
            )
        except FileNotFoundError:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return lease.ProcessLivenessEvidence(exists=False)
            except (PermissionError, OSError):
                return lease.ProcessLivenessEvidence(exists=None)
            return lease.ProcessLivenessEvidence(exists=None)
        except (OSError, UnicodeError, ValueError, IndexError, StopIteration):
            return lease.ProcessLivenessEvidence(exists=None)

    try:
        import psutil

        process = psutil.Process(pid)
        return lease.ProcessLivenessEvidence(
            exists=True,
            process_started_at=_utc_timestamp(float(process.create_time())),
        )
    except ImportError:
        return lease.ProcessLivenessEvidence(exists=None)
    except Exception as exc:
        try:
            import psutil

            if isinstance(exc, psutil.NoSuchProcess):
                return lease.ProcessLivenessEvidence(exists=False)
        except Exception:
            pass
        return lease.ProcessLivenessEvidence(exists=None)


def _make_local_runtime_identity(settings, lease=None):
    """Bind lease recovery to this addon's process-lifetime identity."""

    lease = lease or _import_document_lease()
    profile_id = str(
        settings.get("profile_instance_id") or settings.get("instance_id") or ""
    )
    try:
        uuid.UUID(profile_id)
    except (AttributeError, TypeError, ValueError):
        # Ordinary profiles predate persisted profile IDs. A stable UUIDv5 of
        # the profile path is identification only; it is never an auth secret.
        profile_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                "freecad-mcp-profile:" + _profile_fingerprint(),
            )
        )
    evidence = _probe_process_liveness(os.getpid())
    return lease.LocalRuntimeIdentity(
        addon_profile_id=profile_id,
        addon_runtime_id=_ADDON_RUNTIME_ID,
        freecad_pid=os.getpid(),
        freecad_process_started_at=evidence.process_started_at or "",
        boot_id=_boot_identity(),
        hostname=platform.node(),
    )


def _require_authenticated_lease_runtime(profile_id):
    """Return the exact lease identity used to build the RPC manifest."""

    runtime = getattr(document_lease_service, "local_runtime_identity", None)
    if (
        runtime is None
        or not runtime.freecad_process_started_at
        or not runtime.boot_id
        or not runtime.hostname
    ):
        raise RuntimeError("trusted FreeCAD process/boot/host identity is unavailable")
    if (
        runtime.addon_profile_id != profile_id
        or runtime.addon_runtime_id != rpc_server_runtime_id
        or runtime.freecad_pid != os.getpid()
    ):
        raise RuntimeError(
            "lease runtime identity disagrees with authenticated startup"
        )
    return runtime


def _profile_fingerprint():
    try:
        profile = os.path.realpath(FreeCAD.getUserAppDataDir())
    except Exception:
        profile = "unknown-profile"
    return hashlib.sha256(os.path.normcase(profile).encode("utf-8")).hexdigest()


def _freecad_version_parts():
    value = getattr(FreeCAD, "Version", ())
    value = value() if callable(value) else value
    return tuple(str(part) for part in (value or ()))


_SAVE_VALIDATION_MARKER = "__FREECAD_MCP_SAVE_VALIDATION__"


def _saved_document_expectations(document):
    """Capture the live invariants that the reopened FCStd must preserve."""
    objects = sorted(
        str(getattr(item, "Name", ""))
        for item in getattr(document, "Objects", ())
        if getattr(item, "Name", None)
    )
    bodies = {}
    for item in getattr(document, "Objects", ()):
        if str(getattr(item, "TypeId", "")) != "PartDesign::Body":
            continue
        group = sorted(
            str(getattr(member, "Name", ""))
            for member in getattr(item, "Group", ())
            if getattr(member, "Name", None)
        )
        tip = getattr(getattr(item, "Tip", None), "Name", None)
        bodies[str(item.Name)] = {"members": group, "tip": tip}
    return {"objects": objects, "bodies": bodies}


def _validate_saved_document_worker(path, document_name, profile, expected):
    """Reopen and recompute the saved file in the matching FreeCADCmd worker."""
    manager = worker_manager
    if manager is None:
        return {"ok": False, "error": "matching FreeCADCmd worker is unavailable"}
    workspace = manager.create_workspace()
    safe_name = re.sub(r"[^A-Za-z0-9_]", "_", str(document_name or "Document"))
    if not safe_name or safe_name[0].isdigit():
        safe_name = "Document_" + safe_name
    load_path = workspace / "load" / f"{safe_name}.FCStd"
    snapshot = {
        "ok": True,
        "primary_document": safe_name,
        "snapshot_duration_ms": 0.0,
        "active_document": safe_name,
        "selection": [],
        "documents": [
            {
                "document_name": safe_name,
                "document_label": safe_name,
                "document_uid": "",
                "document_id": "",
                "original_filename": str(path),
                "modified": False,
                "object_count": len(expected.get("objects", ())),
                "dependencies": [],
                "has_pending_transaction": False,
                "transacting": False,
                "last_modified_date": "",
                "snapshot_filename": os.path.basename(path),
                "snapshot_path": str(path),
                "load_filename": load_path.name,
                "load_path": str(load_path),
                "primary": True,
            }
        ],
        "expected_links": [],
        "link_policy": "strict",
        "state_indicators_best_effort": True,
    }
    code = f"""\
import json
doc = FreeCAD.ActiveDocument
errors = []
objects = sorted(obj.Name for obj in doc.Objects)
bodies = {{}}
for obj in doc.Objects:
    shape = getattr(obj, "Shape", None)
    if shape is not None and hasattr(shape, "isNull") and not shape.isNull():
        if hasattr(shape, "isValid") and not shape.isValid():
            errors.append("invalid_shape:" + obj.Name)
    if getattr(obj, "TypeId", "") == "PartDesign::Body":
        members = sorted(item.Name for item in getattr(obj, "Group", []))
        tip = getattr(getattr(obj, "Tip", None), "Name", None)
        if tip is not None and tip not in members:
            errors.append("body_tip_not_member:" + obj.Name + ":" + tip)
        bodies[obj.Name] = {{"members": members, "tip": tip}}
print({_SAVE_VALIDATION_MARKER!r} + json.dumps({{"objects": objects, "bodies": bodies, "errors": errors}}, sort_keys=True))
"""
    result = manager.execute(
        code,
        {"timeout_seconds": 120, "recompute": "target"},
        snapshot,
        workspace,
    )
    if not result.get("success"):
        return {
            "ok": False,
            "profile": profile,
            "error": result.get("error") or result.get("message") or "worker failed",
            "error_code": result.get("error_code"),
        }
    output = str(result.get("message") or "")
    marker_at = output.find(_SAVE_VALIDATION_MARKER)
    if marker_at < 0:
        return {"ok": False, "error": "worker validation result was missing"}
    encoded = output[marker_at + len(_SAVE_VALIDATION_MARKER) :].splitlines()[0]
    try:
        actual = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        return {"ok": False, "error": f"invalid worker validation result: {exc}"}
    differences = {}
    if actual.get("objects") != expected.get("objects"):
        differences["objects"] = {
            "expected": expected.get("objects"),
            "actual": actual.get("objects"),
        }
    if actual.get("bodies") != expected.get("bodies"):
        differences["bodies"] = {
            "expected": expected.get("bodies"),
            "actual": actual.get("bodies"),
        }
    if actual.get("errors"):
        differences["errors"] = actual["errors"]
    return {
        "ok": not differences,
        "worker_reopened": True,
        "recomputed": True,
        "profile": profile,
        "differences": differences,
    }


# Settings persistence is centralized in ``rpc_server.settings``.  Keep the
# imported names above for compatibility with InitGui and existing callers.


def _set_feature_bool(feature, property_names, value):
    """Set a boolean PartDesign property using version-compatible names."""
    properties = set(getattr(feature, "PropertiesList", []))
    for name in property_names:
        if name in properties:
            setattr(feature, name, bool(value))
            return name
    if value:
        raise AttributeError(
            f"{getattr(feature, 'TypeId', 'Feature')} does not support any of: "
            + ", ".join(property_names)
        )
    return None


def _set_extrusion_symmetric(feature, value):
    """Set symmetric pad/pocket extrusion without touching deprecated Midplane."""
    properties = set(getattr(feature, "PropertiesList", []))
    if "SideType" in properties:
        candidates = ("Two sides", "Symmetric") if value else ("One side",)
        last_error = None
        for candidate in candidates:
            try:
                feature.SideType = candidate
                return "SideType"
            except Exception as err:
                last_error = err
        if last_error:
            raise last_error
    if "Symmetric" in properties:
        feature.Symmetric = bool(value)
        return "Symmetric"
    if "Midplane" in properties:
        if value:
            feature.Midplane = True
            return "Midplane"
        return None
    if value:
        raise AttributeError(
            f"{getattr(feature, 'TypeId', 'Feature')} does not support symmetric extrusion"
        )
    return None


# --- Request identity (MCP instance headers → thread-local) ---


def _import_document_lock():
    """Import document_lock under FreeCAD (addon on path) or unit-test package path."""
    try:
        import document_lock as mod

        return mod
    except ImportError:
        from addon.FreeCADMCP import document_lock as mod

        return mod


def _import_document_lease():
    """Import the FreeCAD-independent lease-v2 package in both addon layouts."""
    try:
        # Prefer the repository/package spelling when it is importable. Tests
        # may also place the addon directory directly on sys.path; selecting
        # the top-level spelling first would create duplicate FileBaseline and
        # LeaseCredential classes whose isinstance checks depend on test order.
        from addon.FreeCADMCP import document_lease as mod

        return mod
    except ImportError:
        import document_lease as mod

        return mod


def _redact_rpc_diagnostic(value, *, identity=None, inflight=None):
    """Return bounded diagnostic text with exact request secrets removed."""

    if isinstance(value, (dict, list, tuple)):
        value = redact_lease_protocol_details(value)
    text = str(value)
    if identity is None:
        try:
            identity = _import_document_lock().get_request_identity()
        except Exception:
            identity = {}
    secrets = {
        str(identity.get("rpc_session_token") or ""),
        str(identity.get("lease_token") or ""),
    }
    for item in identity.get("lease_credentials") or ():
        if isinstance(item, dict):
            secrets.add(str(item.get("token") or ""))
    if inflight is not None:
        secrets.update(item.token for item in inflight.credentials)
    for secret in tuple(secrets):
        if not secret:
            continue
        fingerprint = "sha256:" + hashlib.sha256(
            secret.encode("utf-8")
        ).hexdigest()
        text = text.replace(secret, "<redacted>")
        text = text.replace(fingerprint, "<redacted>")
    return text[:2048]


def _lease_service_error(exc, *, request_id=None):
    """Convert lease-core failures to a bounded, token-free RPC result."""
    code = getattr(exc, "code", "LEASE_SERVICE_ERROR")
    result = {
        "success": False,
        "ok": False,
        "error_code": code,
        "error": _redact_rpc_diagnostic(exc),
    }
    details = getattr(exc, "details", None)
    if details:
        # Service errors may include nested coordination records. Keep this
        # boundary independently safe even if a future exception accidentally
        # carries a credential digest or bearer-token-shaped field.
        result["details"] = redact_lease_protocol_details(details)
    if request_id:
        result["request_id"] = request_id
    return result


def _ensure_v2_document(document):
    if document_identity_service is None:
        raise RuntimeError("document lease service is not initialized")
    if document_lease_service is None:
        return document_identity_service.register_document(document)
    try:
        from document_lease.observer import register_live_document_recovery
    except ImportError:
        from addon.FreeCADMCP.document_lease.observer import (
            register_live_document_recovery,
        )
    identity, imported = register_live_document_recovery(
        document_lease_service, document
    )
    if imported is not None:
        try:
            from lock_indicator import refresh_lock_indicator

            refresh_lock_indicator()
        except Exception:
            logger.debug(
                "Could not queue foreign recovery status refresh", exc_info=True
            )
    return identity


def _live_document_from_selector(selector):
    """Resolve a selector only against currently open FreeCAD documents."""
    if not isinstance(selector, dict):
        raise ValueError("DocumentSelector must be an object")
    name = selector.get("document_name") or ""
    session_uuid = selector.get("document_session_uuid") or ""
    canonical_path = selector.get("canonical_path") or ""
    if name:
        document = FreeCAD.getDocument(str(name))
        if document is None:
            raise ValueError(f"Document {name!r} is not open")
        identity = _ensure_v2_document(document)
    else:
        document = None
        identity = None
        for candidate in FreeCAD.listDocuments().values():
            candidate_identity = _ensure_v2_document(candidate)
            if session_uuid and candidate_identity.session_uuid == session_uuid:
                document, identity = candidate, candidate_identity
                break
            if canonical_path:
                try:
                    resolved = document_identity_service.resolve(
                        {"canonical_path": canonical_path}
                    )
                except Exception:
                    continue
                if resolved.session_uuid == candidate_identity.session_uuid:
                    document, identity = candidate, candidate_identity
                    break
        if document is None or identity is None:
            raise ValueError("DocumentSelector does not identify an open document")
    asserted = document_identity_service.resolve(selector)
    if asserted.session_uuid != identity.session_uuid:
        raise ValueError("DocumentSelector fields identify different documents")
    return document, asserted


def _credential_from_wire(payload, identity=None):
    lease = _import_document_lease()
    if not isinstance(payload, dict):
        raise lease.AuthorizationError("a complete LeaseCredential is required")
    try:
        request_identity = dict(
            identity or _import_document_lock().get_request_identity()
        )
        authenticated_runtime_id = str(
            request_identity.get("instance_id")
            if request_identity.get("authenticated_session_id")
            else ""
        )
        return lease.LeaseCredential(
            lease_id=str(payload["lease_id"]),
            document_session_uuid=str(payload["document_session_uuid"]),
            generation=int(payload["generation"]),
            token=str(payload["token"]),
            mcp_instance_id=authenticated_runtime_id,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise lease.AuthorizationError(
            "lease id, document, generation, token, and authenticated runtime are required"
        ) from exc


def _credential_for_document(document_name, identity=None):
    identity = dict(identity or _import_document_lock().get_request_identity())
    document = FreeCAD.getDocument(document_name)
    if document is None:
        raise ValueError(f"Document {document_name!r} is not open")
    document_identity = _ensure_v2_document(document)
    matches = [
        item
        for item in identity.get("lease_credentials") or []
        if isinstance(item, dict)
        and item.get("document_session_uuid") == document_identity.session_uuid
    ]
    if len(matches) != 1:
        lease = _import_document_lease()
        raise lease.AuthorizationError(
            "request must contain exactly one credential for the selected document"
        )
    return _credential_from_wire(matches[0], identity), document_identity


def _credential_for_selector(selector, identity=None):
    identity = dict(identity or _import_document_lock().get_request_identity())
    document, document_identity = _live_document_from_selector(selector)
    matches = [
        item
        for item in identity.get("lease_credentials") or []
        if isinstance(item, dict)
        and item.get("document_session_uuid") == document_identity.session_uuid
    ]
    if len(matches) != 1:
        lease = _import_document_lease()
        raise lease.AuthorizationError(
            "request must contain exactly one credential for the selected document"
        )
    return _credential_from_wire(matches[0], identity), document_identity, document


def _effective_sidecar_block(document, request_identity):
    """Block active or unreadable v2 sidecars in every compatibility mode."""

    path = str(getattr(document, "FileName", "") or "")
    if not path:
        return None
    lease = _import_document_lease()
    sidecar = lease.sidecar_path_for(path)
    if not os.path.lexists(sidecar):
        return None
    store = (
        document_lease_service.sidecar_store
        if document_lease_service is not None
        else lease.SidecarStore(strict_permissions=False, allow_network=True)
    )
    try:
        persisted = store.read(sidecar)
    except Exception as exc:
        return {
            "success": False,
            "error_code": "SIDECAR_UNKNOWN",
            "error": (
                "A document lease sidecar exists but cannot be validated; "
                f"writes remain blocked: {str(exc)[:1024]}"
            ),
        }

    if document_lease_service is not None:
        try:
            identity = _ensure_v2_document(document)
            local = document_lease_service.get(
                {"document_session_uuid": identity.session_uuid}
            )
            if local is not None:
                credential, _identity = _credential_for_document(
                    document.Name, request_identity
                )
                document_lease_service.authorize(
                    credential,
                    selector={"document_session_uuid": identity.session_uuid},
                )
                return None
        except Exception:
            pass
    return {
        "success": False,
        "error_code": "DOCUMENT_LEASE_CONFLICT",
        "error": "A v2 document lease owns this file; this request is read-only",
        "lease": persisted.to_public_dict(),
    }


def _live_validation_evidence(document, document_identity, record):
    """Build release evidence without hashing the document on Qt.

    Clean release is allowed only for a record whose verified baseline is at
    least as new as its final mutation.  The immediate GUI-thread check uses
    that baseline's stat metadata plus the live document/file identity; the
    full SHA and worker validation were already completed at save promotion.
    """

    lease = _import_document_lease()
    live = document_identity_service.inspect_registered_document(
        document_identity.session_uuid, document
    )
    _assert_mutation_file_metadata_unchanged(record)
    baseline_current = bool(
        record.baseline is not None
        and record.validation_complete
        and record.last_verified_save_revision >= record.last_mutation_revision
    )
    return lease.LiveDocumentValidation(
        document=live,
        document_modified=require_document_modified(document),
        baseline=record.baseline,
        baseline_validated=baseline_current,
    )


def _assert_mutation_file_metadata_unchanged(record):
    """Reject an externally changed saved file before a GUI mutation starts.

    Full SHA-256 verification remains outside the GUI thread at acquisition and
    save boundaries.  This immediate GUI-thread check compares the stable file
    identity (already re-resolved by ``_credential_for_document``), size, and
    nanosecond mtime so queued work cannot proceed after an ordinary external
    replacement or edit.
    """

    lease = _import_document_lease()
    path = record.document.canonical_path
    if not path:
        return
    baseline = record.baseline
    if baseline is None:
        raise lease.LiveDocumentValidationError(
            "saved lease has no verified file baseline"
        )
    try:
        current = os.stat(path)
    except OSError as exc:
        raise lease.LiveDocumentValidationError(
            f"leased document file is unavailable: {exc}"
        ) from exc
    if int(current.st_size) != baseline.size:
        raise lease.LiveDocumentValidationError(
            "leased document file size changed externally"
        )
    if int(current.st_mtime_ns) != baseline.mtime_ns:
        raise lease.LiveDocumentValidationError(
            "leased document modification time changed externally"
        )


def _discard_terminal_snapshot(terminal):
    snapshot_id = (
        terminal.get("document_state", {}).get("snapshot_id")
        if isinstance(terminal, dict)
        else None
    )
    if snapshot_id:
        try:
            discard_lease_baseline_snapshot(snapshot_id)
        except Exception:
            logger.warning(
                "Released lease but could not remove recovery snapshot %s",
                snapshot_id,
                exc_info=True,
            )


def _v2_status_for_context(context):
    if document_lease_service is None:
        return []
    document_ids = {
        item.get("document_session_uuid")
        for item in context.get("identity", {}).get("lease_credentials", [])
        if isinstance(item, dict)
    }
    return [
        record
        for record in document_lease_service.list_records()
        if record.get("document", {}).get("session_uuid") in document_ids
    ]


class McpIdentityRequestHandler(SimpleXMLRPCRequestHandler):
    """Capture MCP identity / lease headers into document_lock thread-local."""

    def do_POST(self):
        try:
            document_lock = _import_document_lock()
            headers = self.headers
            pid_raw = headers.get("X-MCP-Pid")
            port_raw = headers.get("X-MCP-Rpc-Port")
            try:
                pid = int(pid_raw) if pid_raw not in (None, "") else None
            except (TypeError, ValueError):
                pid = None
            try:
                rpc_port = int(port_raw) if port_raw not in (None, "") else None
            except (TypeError, ValueError):
                rpc_port = None
            generation_raw = headers.get("X-MCP-Lease-Generation")
            try:
                lease_generation = (
                    int(generation_raw) if generation_raw not in (None, "") else None
                )
            except (TypeError, ValueError):
                lease_generation = None
            credential_header = headers.get("X-MCP-Lease-Credentials") or ""
            lease_credentials = []
            if credential_header:
                if len(credential_header) > 32768:
                    raise ValueError("lease credential header is too large")
                parsed_credentials = json.loads(credential_header)
                if (
                    not isinstance(parsed_credentials, list)
                    or len(parsed_credentials) > 32
                ):
                    raise ValueError("lease credential header is invalid")
                lease_credentials = [
                    item for item in parsed_credentials if isinstance(item, dict)
                ]
            document_lock.set_request_identity(
                instance_id=headers.get("X-MCP-Instance-Id") or None,
                client=headers.get("X-MCP-Client") or None,
                pid=pid,
                host=headers.get("X-MCP-Host") or None,
                lease_token=headers.get("X-MCP-Lease-Token") or None,
                rpc_port=rpc_port,
                request_id=headers.get("X-MCP-Request-Id") or None,
                rpc_session_token=headers.get("X-MCP-Session-Token") or None,
                lease_id=headers.get("X-MCP-Lease-Id") or None,
                lease_generation=lease_generation,
                document_session_uuid=(
                    headers.get("X-MCP-Document-Session-Id") or None
                ),
                lease_credentials=lease_credentials,
            )
        except Exception:
            pass
        try:
            return super().do_POST()
        finally:
            try:
                _import_document_lock().clear_request_identity()
            except Exception:
                pass


# --- IP-filtered XML-RPC server ---

_XMLRPC_INT_MIN = -(2**31)
_XMLRPC_INT_MAX = (2**31) - 1


def _xmlrpc_safe_response(value):
    """Return a response value encodable by the stdlib XML-RPC marshaller.

    Python's XML-RPC encoder supports only signed 32-bit ``int`` values even
    though lease/save results legitimately contain nanosecond timestamps and
    large file sizes.  Keep protocol booleans and ordinary integers typed, but
    carry out-of-range values as unambiguous decimal strings.  This conversion
    is intentionally outbound-only; addon state and sidecars retain integers.
    """

    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if _XMLRPC_INT_MIN <= value <= _XMLRPC_INT_MAX:
            return value
        return str(value)
    if isinstance(value, dict):
        return {key: _xmlrpc_safe_response(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_xmlrpc_safe_response(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_xmlrpc_safe_response(item) for item in value)
    return value


class FilteredXMLRPCServer(SimpleXMLRPCServer):
    """IP-filtered server with separate bounded general/control capacity."""

    CONTROL_METHODS = frozenset(
        {
            "ping",
            "handshake_v2",
            "invoke_v2_control",
            "lease_heartbeat_batch",
            "lease_reconcile",
            "get_request_status",
            "cancel_request",
            "get_worker_status",
            "cancel_worker_job",
            "shutdown_rpc_server",
        }
    )

    def __init__(self, addr, allowed_ips_str="127.0.0.1", **kwargs):
        self._allowed_networks = _parse_allowed_ips(allowed_ips_str)
        self._handler_slots = threading.BoundedSemaphore(5)
        self._general_slots = threading.BoundedSemaphore(3)
        self._control_slots = threading.BoundedSemaphore(2)
        self._handler_executor = ThreadPoolExecutor(
            max_workers=5, thread_name_prefix="FreeCADMCP-RPC"
        )
        self._accepting_requests = True
        self._accepting_lock = threading.Lock()
        kwargs.setdefault("requestHandler", McpIdentityRequestHandler)
        super().__init__(addr, **kwargs)

    def process_request(self, request, client_address):
        with self._accepting_lock:
            admitted = self._accepting_requests and self._handler_slots.acquire(False)
        if not admitted:
            self.shutdown_request(request)
            return
        try:
            self._handler_executor.submit(
                self._process_request_in_pool, request, client_address
            )
        except Exception:
            self._handler_slots.release()
            self.shutdown_request(request)
            raise

    def _process_request_in_pool(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)
            self._handler_slots.release()

    def _marshaled_dispatch(self, data, dispatch_method=None, path=None):
        """Route parsed XML-RPC methods through independent bounded slots."""
        try:
            _params, method = xmlrpc_loads(data)
        except Exception:
            return super()._marshaled_dispatch(data, dispatch_method, path)
        control = method in self.CONTROL_METHODS
        slots = self._control_slots if control else self._general_slots
        with self._accepting_lock:
            accepting = self._accepting_requests
        if not accepting:
            return xmlrpc_dumps(
                Fault(503, "server_stopping"),
                methodresponse=True,
                allow_none=self.allow_none,
                encoding=self.encoding,
            ).encode(self.encoding, "xmlcharrefreplace")
        if not slots.acquire(blocking=False):
            lane = "control" if control else "general"
            return xmlrpc_dumps(
                Fault(503, f"server_busy: {lane} request capacity is full"),
                methodresponse=True,
                allow_none=self.allow_none,
                encoding=self.encoding,
            ).encode(self.encoding, "xmlcharrefreplace")
        try:
            dispatch = dispatch_method or self._dispatch

            def dispatch_with_safe_response(method_name, method_params):
                return _xmlrpc_safe_response(dispatch(method_name, method_params))

            return super()._marshaled_dispatch(data, dispatch_with_safe_response, path)
        finally:
            slots.release()

    def begin_shutdown(self):
        with self._accepting_lock:
            self._accepting_requests = False

    def server_close(self):
        self.begin_shutdown()
        super().server_close()
        self._handler_executor.shutdown(wait=False, cancel_futures=False)

    def verify_request(self, request, client_address):
        client_ip = client_address[0]
        try:
            addr = ipaddress.ip_address(client_ip)
            for network in self._allowed_networks:
                if addr in network:
                    return True
        except ValueError:
            pass
        logger.warning("MCP RPC: rejected connection from %s", client_ip)
        return False


_COMMA_SEP_RE = re.compile(r"^\s*[^,\s]+(\s*,\s*[^,\s]+)*\s*$")


def validate_allowed_ips(allowed_ips_str):
    """Validate a comma-separated string of IP addresses/subnets.

    Returns a ``(valid, errors)`` tuple.  ``valid`` is a list of normalised
    entry strings that passed validation; ``errors`` is a list of
    human-readable error messages (empty when the input is fully valid).

    Checks performed:
    1. The overall string is well-formed comma-separated (no leading/trailing
       commas, no empty entries between commas, not blank).
    2. Each individual entry is a valid IPv4/IPv6 address or CIDR subnet
       (validated via the stdlib ``ipaddress`` module).
    """
    errors = []

    if not allowed_ips_str or not allowed_ips_str.strip():
        return [], ["Input must not be empty."]

    if not _COMMA_SEP_RE.match(allowed_ips_str):
        return [], [
            "Malformed list — check for leading/trailing commas, "
            "double commas, or missing separators."
        ]

    valid = []
    for entry in allowed_ips_str.split(","):
        entry = entry.strip()
        try:
            ipaddress.ip_network(entry, strict=False)
            valid.append(entry)
        except ValueError:
            errors.append(f"Invalid IP/subnet: '{entry}'")
    return valid, errors


def _parse_allowed_ips(allowed_ips_str):
    """Parse a comma-separated string of IPs/subnets into a list of ip_network objects."""
    valid, errors = validate_allowed_ips(allowed_ips_str)
    for msg in errors:
        logger.warning("MCP RPC: %s, skipping", msg)
    return [ipaddress.ip_network(entry, strict=False) for entry in valid]


@dataclass
class Object:
    name: str
    type: str | None = None
    analysis: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)


def set_object_property(
    doc: FreeCAD.Document, obj: FreeCAD.DocumentObject, properties: dict[str, Any]
):
    for prop, val in properties.items():
        try:
            if prop in obj.PropertiesList:
                if prop == "Placement" and isinstance(val, dict):
                    if "Base" in val:
                        pos = val["Base"]
                    elif "Position" in val:
                        pos = val["Position"]
                    else:
                        pos = {}
                    rot = val.get("Rotation", {})
                    placement = FreeCAD.Placement(
                        FreeCAD.Vector(
                            pos.get("x", 0),
                            pos.get("y", 0),
                            pos.get("z", 0),
                        ),
                        FreeCAD.Rotation(
                            FreeCAD.Vector(
                                rot.get("Axis", {}).get("x", 0),
                                rot.get("Axis", {}).get("y", 0),
                                rot.get("Axis", {}).get("z", 1),
                            ),
                            rot.get("Angle", 0),
                        ),
                    )
                    setattr(obj, prop, placement)

                elif isinstance(getattr(obj, prop), FreeCAD.Vector) and isinstance(
                    val, dict
                ):
                    vector = FreeCAD.Vector(
                        val.get("x", 0), val.get("y", 0), val.get("z", 0)
                    )
                    setattr(obj, prop, vector)

                elif prop in ["Base", "Tool", "Source", "Profile"] and isinstance(
                    val, str
                ):
                    ref_obj = doc.getObject(val)
                    if ref_obj:
                        setattr(obj, prop, ref_obj)
                    else:
                        raise ValueError(f"Referenced object '{val}' not found.")

                elif prop == "References" and isinstance(val, list):
                    refs = []
                    for ref_name, face in val:
                        ref_obj = doc.getObject(ref_name)
                        if ref_obj:
                            refs.append((ref_obj, face))
                        else:
                            raise ValueError(
                                f"Referenced object '{ref_name}' not found."
                            )
                    setattr(obj, prop, refs)

                else:
                    setattr(obj, prop, val)
            # ShapeColor is a property of the ViewObject
            elif prop == "ShapeColor" and isinstance(val, (list, tuple)):
                setattr(
                    obj.ViewObject,
                    prop,
                    (float(val[0]), float(val[1]), float(val[2]), float(val[3])),
                )

            elif prop == "ViewObject" and isinstance(val, dict):
                for k, v in val.items():
                    if k == "ShapeColor":
                        setattr(
                            obj.ViewObject,
                            k,
                            (float(v[0]), float(v[1]), float(v[2]), float(v[3])),
                        )
                    else:
                        setattr(obj.ViewObject, k, v)

            else:
                setattr(obj, prop, val)

        except Exception as e:
            FreeCAD.Console.PrintError(f"Property '{prop}' assignment error: {e}\n")


class FreeCADRPC:
    """RPC server for FreeCAD"""

    TIMEOUT = 30
    EXECUTE_TIMEOUT = 120

    def __init__(self, allow_execute_code: bool = True):
        self.allow_execute_code = allow_execute_code
        # XML-RPC handlers run concurrently.  A handler publishes immutable
        # authorization context here only while it calls a public RPC method;
        # _dispatch_gui captures a copy into the queued Qt closure.
        self._mutation_context = threading.local()
        self._inflight_context = threading.local()

    def _current_inflight(self):
        return getattr(self._inflight_context, "value", None)

    def _request_checkpoint(self, phase):
        inflight = self._current_inflight()
        if inflight is None:
            return None
        return inflight.token.checkpoint(phase)

    @staticmethod
    def _model_credential(inflight_credential):
        lease = _import_document_lease()
        return lease.LeaseCredential(
            lease_id=inflight_credential.lease_id,
            document_session_uuid=inflight_credential.document_session_uuid,
            generation=inflight_credential.generation,
            token=inflight_credential.token,
            mcp_instance_id=inflight_credential.mcp_instance_id,
        )

    def _retain_inflight_credential(self, credential):
        """Retain a credential created mid-request until actual completion."""

        inflight = self._current_inflight()
        if inflight is None:
            return
        inflight.add_credentials(
            (
                InflightLeaseCredential(
                    lease_id=credential.lease_id,
                    document_session_uuid=credential.document_session_uuid,
                    generation=credential.generation,
                    token=credential.token,
                    mcp_instance_id=credential.mcp_instance_id,
                ),
            )
        )
        inflight.touch_credentials(
            (
                InflightLeaseCredential(
                    lease_id=credential.lease_id,
                    document_session_uuid=credential.document_session_uuid,
                    generation=credential.generation,
                    token=credential.token,
                    mcp_instance_id=credential.mcp_instance_id,
                ),
            )
        )

    def _touch_inflight_credential(self, credential, inflight=None):
        inflight = inflight or self._current_inflight()
        if inflight is None:
            return
        inflight.touch_credentials(
            (
                InflightLeaseCredential(
                    lease_id=credential.lease_id,
                    document_session_uuid=credential.document_session_uuid,
                    generation=credential.generation,
                    token=credential.token,
                    mcp_instance_id=credential.mcp_instance_id,
                ),
            )
        )

    @staticmethod
    def _finish_cancellation_resolution(inflight, result):
        """Publish one authoritative result and retire terminal credentials."""

        return rpc_inflight_request_registry.finish_cancellation_resolution(
            inflight, result
        )

    @staticmethod
    def _wait_for_cancellation_resolution(inflight, *, wait_timeout=None):
        """Wait for the resolver owner; never publish a speculative result."""

        if not inflight.token.wait_cancellation_resolution(wait_timeout):
            raise RuntimeError(
                "Cancellation resolution remains owned by another request phase"
            )
        resolved = inflight.token.cancellation_resolution()
        rpc_inflight_request_registry.refresh_terminal(
            inflight.session_id, inflight.request_id
        )
        return resolved or []

    def _complete_request_cancellation(
        self, inflight, *, dirty=None, snapshot_id=None
    ):
        """Resolve typed lease cancellation after the request's actual phase ends."""

        if inflight is None:
            return []
        snapshot = inflight.token.snapshot()
        if not snapshot.cancellation_requested:
            return []
        wait_timeout = 0.0 if shutdown_requested.is_set() else None
        if inflight.method in {"acquire_document_lock", "create_document"}:
            claimed, cached = inflight.token.claim_cancellation_resolution()
            if not claimed:
                if cached is not None:
                    rpc_inflight_request_registry.refresh_terminal(
                        inflight.session_id, inflight.request_id
                    )
                    return cached
                return self._wait_for_cancellation_resolution(
                    inflight, wait_timeout=wait_timeout
                )
            results = []
            may_have_mutated = bool(snapshot.mutation_started or snapshot.uncertain)
            if document_lease_service is not None:
                for private in inflight.affected_credentials:
                    credential = self._model_credential(private)
                    try:
                        if may_have_mutated:
                            record = (
                                document_lease_service.fail_acquisition_after_mutation(
                                    credential,
                                    message=(
                                        "Acquisition was cancelled after mutation began"
                                    ),
                                    request_id=inflight.request_id,
                                    dirty=True,
                                    snapshot_id=snapshot_id,
                                )
                            )
                            results.append(record.to_public_dict())
                        else:
                            results.append(
                                document_lease_service.abort_acquisition(credential)
                            )
                    except Exception as exc:
                        results.append(
                            {
                                "success": False,
                                "error_code": _redact_rpc_diagnostic(
                                    getattr(exc, "code", type(exc).__name__.upper()),
                                    inflight=inflight,
                                ),
                                "error": _redact_rpc_diagnostic(
                                    exc, inflight=inflight
                                ),
                            }
                        )
            return self._finish_cancellation_resolution(inflight, results)
        begin_result = self._begin_request_cancellation(
            inflight, wait_timeout=wait_timeout
        )
        if begin_result is None:
            # A different phase owns the authority-changing transition. During
            # shutdown we skip unsafe completion instead of interleaving with
            # that owner or waiting without a bound.
            raise RuntimeError(
                "Cancellation fencing remains owned by another request phase"
            )
        if not inflight.lease_affecting or document_lease_service is None:
            claimed, cached = inflight.token.claim_cancellation_resolution()
            if claimed:
                return self._finish_cancellation_resolution(inflight, [])
            if cached is not None:
                rpc_inflight_request_registry.refresh_terminal(
                    inflight.session_id, inflight.request_id
                )
                return cached
            return self._wait_for_cancellation_resolution(
                inflight, wait_timeout=wait_timeout
            )
        claimed, cached = inflight.token.claim_cancellation_resolution()
        if not claimed:
            if cached is not None:
                rpc_inflight_request_registry.refresh_terminal(
                    inflight.session_id, inflight.request_id
                )
                return cached
            return self._wait_for_cancellation_resolution(
                inflight, wait_timeout=wait_timeout
            )
        may_have_mutated = bool(snapshot.mutation_started or snapshot.uncertain)
        results = []
        try:
            for private in inflight.affected_credentials:
                credential = self._model_credential(private)
                try:
                    document_lease_service.begin_cancellation(
                        credential,
                        request_id=inflight.request_id,
                        operation="Cancelling authenticated request",
                        mutation_may_have_begun=may_have_mutated,
                    )
                    completed = document_lease_service.complete_cancellation(
                        credential,
                        request_id=inflight.request_id,
                        mutation_may_have_begun=may_have_mutated,
                        dirty=dirty,
                    )
                    results.append(completed.to_public_dict())
                except Exception as exc:
                    # Cancellation must remain fail-closed.  If another phase
                    # already resolved the exact event, the service is
                    # idempotent; other failures remain in request diagnostics.
                    results.append(
                        {
                            "success": False,
                            "error_code": _redact_rpc_diagnostic(
                                getattr(exc, "code", type(exc).__name__.upper()),
                                inflight=inflight,
                            ),
                            "error": _redact_rpc_diagnostic(exc, inflight=inflight),
                        }
                    )
            return self._finish_cancellation_resolution(inflight, results)
        except Exception:
            self._finish_cancellation_resolution(inflight, results)
            raise

    def _begin_request_cancellation(self, inflight, *, wait_timeout=None):
        """Commit the single CANCELLING event before queue removal/completion."""

        if inflight is None or not inflight.token.snapshot().cancellation_requested:
            return []
        if inflight.method in {"acquire_document_lock", "create_document"}:
            return []
        if not inflight.token.claim_cancellation_begin():
            # Do not race completion/CAS rollback ahead of the thread that
            # owns the CANCELLING transition.  Its finally block always
            # signals, even if sidecar coordination raises.
            if not inflight.token.wait_cancellation_begin(wait_timeout):
                return None
            return []
        results = []
        try:
            if not inflight.lease_affecting or document_lease_service is None:
                return results
            snapshot = inflight.token.snapshot()
            for private in inflight.affected_credentials:
                try:
                    record = document_lease_service.begin_cancellation(
                        self._model_credential(private),
                        request_id=inflight.request_id,
                        operation="Cancelling authenticated request",
                        mutation_may_have_begun=(
                            snapshot.mutation_started or snapshot.uncertain
                        ),
                    )
                    results.append(record.to_public_dict())
                except Exception as exc:
                    results.append(
                        {
                            "success": False,
                            "error_code": _redact_rpc_diagnostic(
                                getattr(exc, "code", type(exc).__name__.upper()),
                                inflight=inflight,
                            ),
                            "error": _redact_rpc_diagnostic(exc, inflight=inflight),
                        }
                    )
            return results
        finally:
            inflight.token.finish_cancellation_begin()

    def _call_with_mutation_context(self, func, params, context):
        self._mutation_context.value = context
        try:
            return func(*params)
        finally:
            if hasattr(self._mutation_context, "value"):
                del self._mutation_context.value

    def _dispatch(self, method, params):
        """XML-RPC chokepoint: enforce document leases when configured.

        When ``document_lock_enforcement`` is off, behaviour is identical to
        the default SimpleXMLRPCDispatcher instance dispatch.
        """
        try:
            dl = _import_document_lock()
            VerbKind = dl.VerbKind
            annotate_read_result = dl.annotate_read_result
            check_mutation_allowed = dl.check_mutation_allowed
            classify_verb = dl.classify_verb
            extract_referenced_documents_from_code = (
                dl.extract_referenced_documents_from_code
            )
            validate_unsafe_execute_scope = dl.validate_unsafe_execute_scope
            is_enforcement_enabled = dl.is_enforcement_enabled
            resolve_doc_key = dl.resolve_doc_key
        except ImportError:
            func = getattr(self, method, None)
            if func is None or method.startswith("_"):
                raise Exception(f'method "{method}" is not supported')
            return func(*params)

        kind, extractor = classify_verb(method)
        method_spec = make_method_spec(method, kind.value)
        enforce = is_enforcement_enabled()

        # Resolve callable first (also validates method exists)
        func = getattr(self, method, None)
        if func is None or method.startswith("_"):
            raise Exception(f'method "{method}" is not supported')

        if not enforce:
            read_only_execute = (
                method == "execute_code"
                and len(params) > 1
                and isinstance(params[1], dict)
                and bool(params[1].get("read_only", False))
            )
            if (
                method_spec.mutates_live_document
                and not read_only_execute
                and method != "create_document"
            ):
                names = []
                scope_resolution_failed = False
                try:
                    extracted = extractor(
                        params if isinstance(params, tuple) else tuple(params)
                    )
                    if extracted:
                        names.append(str(extracted))
                except Exception:
                    scope_resolution_failed = True
                execute_options = {}
                affected_documents_declared = False
                if (
                    method == "execute_code"
                    and len(params) > 1
                    and isinstance(params[1], dict)
                ):
                    execute_options = params[1]
                    affected = execute_options.get("affected_documents")
                    if isinstance(affected, (list, tuple)):
                        affected_documents_declared = bool(affected) and all(
                            isinstance(name, str) and bool(name.strip())
                            for name in affected
                        )
                        affected_names = affected if affected_documents_declared else ()
                        if affected and not affected_documents_declared:
                            scope_resolution_failed = True
                    else:
                        affected_names = ()
                        if affected is not None:
                            scope_resolution_failed = True
                    for name in (execute_options.get("document"), *affected_names):
                        if isinstance(name, str) and name and name not in names:
                            names.append(name)
                        elif name is not None and not isinstance(name, str):
                            scope_resolution_failed = True
                selector = params[0] if params and isinstance(params[0], dict) else {}
                selected_name = selector.get("document_name")
                if selected_name and selected_name not in names:
                    names.append(str(selected_name))
                selected_path = str(selector.get("canonical_path") or "")
                documents = []
                for name in names:
                    document = FreeCAD.getDocument(name)
                    if document is not None and document not in documents:
                        documents.append(document)
                    elif document is None:
                        scope_resolution_failed = True
                selected_path_resolved = not selected_path
                open_documents = tuple(FreeCAD.listDocuments().values())
                if selected_path:
                    wanted = os.path.normcase(os.path.realpath(selected_path))
                    for document in open_documents:
                        live_path = str(getattr(document, "FileName", "") or "")
                        if (
                            live_path
                            and os.path.normcase(os.path.realpath(live_path)) == wanted
                        ):
                            selected_path_resolved = True
                            if document not in documents:
                                documents.append(document)
                if not selected_path_resolved:
                    scope_resolution_failed = True
                request_identity = dl.get_request_identity()
                sidecar_blocks = []
                for document in open_documents:
                    blocked = _effective_sidecar_block(document, request_identity)
                    if blocked is not None:
                        sidecar_blocks.append((document, blocked))

                if (
                    sidecar_blocks
                    and method == "execute_code"
                    and not (affected_documents_declared)
                ):
                    return {
                        "success": False,
                        "error_code": "FOREIGN_LEASE_SCOPE_REQUIRED",
                        "error": (
                            "Live mutating execute_code requires a non-empty "
                            "affected_documents list while an open document has "
                            "an active or unreadable v2 sidecar"
                        ),
                        "blocked_documents": [
                            {
                                "document_name": str(
                                    getattr(document, "Name", "") or ""
                                ),
                                "error_code": blocked.get(
                                    "error_code", "DOCUMENT_LEASE_CONFLICT"
                                ),
                            }
                            for document, blocked in sidecar_blocks
                        ],
                    }

                scope_resolved = bool(documents) and not scope_resolution_failed
                if sidecar_blocks and not scope_resolved:
                    return {
                        "success": False,
                        "error_code": "FOREIGN_LEASE_SCOPE_UNRESOLVED",
                        "error": (
                            "Mutation scope could not be resolved while an open "
                            "document has an active or unreadable v2 sidecar"
                        ),
                        "blocked_documents": [
                            {
                                "document_name": str(
                                    getattr(document, "Name", "") or ""
                                ),
                                "error_code": blocked.get(
                                    "error_code", "DOCUMENT_LEASE_CONFLICT"
                                ),
                            }
                            for document, blocked in sidecar_blocks
                        ],
                    }

                for document in documents:
                    blocked = next(
                        (
                            result
                            for candidate, result in sidecar_blocks
                            if candidate is document
                        ),
                        None,
                    )
                    if blocked is not None:
                        return blocked
            return func(*params)

        identity = dl.get_request_identity()
        authenticated_methods = {
            "acquire_document_lock",
            "update_document_lock",
            "heartbeat_document_lock",
            "lease_heartbeat_batch",
            "lease_reconcile",
            "release_document_lock",
            "save_document",
            "save_document_as",
            "finalize_document_edit",
            "get_request_status",
            "cancel_request",
            "shutdown_rpc_server",
        }
        read_only_execute = (
            method == "execute_code"
            and len(params) > 1
            and isinstance(params[1], dict)
            and bool(params[1].get("read_only", False))
        )
        requires_authenticated_session = (
            (kind == VerbKind.MUTATING and not read_only_execute)
            or method in authenticated_methods
        ) and method not in {"handshake_v2", "invoke_v2"}
        if requires_authenticated_session:
            if rpc_session_manager is None:
                return {
                    "success": False,
                    "error_code": "LEASE_PROTOCOL_REQUIRED",
                    "error": "Document lease enforce mode requires authenticated RPC v2",
                }
            session_token = identity.get("rpc_session_token")
            runtime_id = identity.get("instance_id")
            if not session_token or not runtime_id:
                return {
                    "success": False,
                    "error_code": "LEASE_PROTOCOL_REQUIRED",
                    "error": (
                        "This operation requires a handshake_v2 session and an "
                        "immutable authenticated request envelope"
                    ),
                }
            try:
                session = rpc_session_manager.authenticate(
                    session_token, mcp_runtime_id=runtime_id
                )
                if not identity.get("authenticated_session_id"):
                    identity["authenticated_session_id"] = session.session_id
                    identity["mcp_process_started_at"] = session.mcp.process_started_at
                    dl.set_request_identity(**identity)
            except Exception as exc:
                error = lease_protocol_public_error(
                    exc, request_id=identity.get("request_id")
                )
                return {
                    "success": False,
                    "error_code": error["error"]["code"],
                    "error": error["error"]["message"],
                    "request_id": error.get("request_id"),
                }

        # --- Enforcement path ---
        doc_name = None
        try:
            doc_name = extractor(params if isinstance(params, tuple) else tuple(params))
        except Exception:
            doc_name = None

        def authorize_document(document_name):
            if document_lease_service is not None:
                try:
                    credential, document_identity = _credential_for_document(
                        document_name, dl.get_request_identity()
                    )
                    allowed_states = {_import_document_lease().LeaseState.LOCKED_IDLE}
                    if method_spec.allowed_during_recovery:
                        allowed_states.add(
                            _import_document_lease().LeaseState.LOCKED_ERROR
                        )
                    record = document_lease_service.authorize(
                        credential,
                        selector={
                            "document_session_uuid": document_identity.session_uuid,
                            "document_name": document_name,
                        },
                        allowed_states=allowed_states,
                    )
                    return {
                        "success": True,
                        "credential": credential,
                        "lease": record.to_public_dict(),
                    }
                except Exception as exc:
                    return _lease_service_error(
                        exc, request_id=dl.get_request_identity().get("request_id")
                    )
            try:
                key = resolve_doc_key(doc_name=document_name)
            except Exception as exc:
                return {
                    "success": False,
                    "error_code": "document_not_locked",
                    "error": f"Cannot resolve document {document_name!r}: {exc}",
                }
            return check_mutation_allowed(key)

        # execute_code / async: explicit document + multi-doc guards
        if method == "execute_code":
            options = (
                params[1] if len(params) > 1 and isinstance(params[1], dict) else {}
            )
            read_only = bool(options.get("read_only", False))
            code = params[0] if params else ""
            if not read_only:
                settings = load_settings()
                generated_operation = bool(options.get("generated_operation"))
                if generated_operation:
                    operation_id = str(options.get("operation_id") or "")
                    supplied_signature = str(options.get("operation_signature") or "")
                    expected_signature = _generated_execute_signature(
                        session_token=identity.get("rpc_session_token") or "",
                        request_id=identity.get("request_id") or "",
                        code=code,
                        options=options,
                    )
                    if not operation_id or not hmac.compare_digest(
                        supplied_signature, expected_signature
                    ):
                        return {
                            "success": False,
                            "error_code": "GENERATED_OPERATION_SIGNATURE_INVALID",
                            "error": (
                                "The internal generated-operation capability "
                                "signature is missing or invalid"
                            ),
                        }
                    # The signed internal identity, rather than the generic
                    # execute_code verb, drives attribution and postflight.
                    # Generated scripts own their detailed transactions and
                    # requested recompute, while the common guard still checks
                    # document/Body/Tip invariants before returning idle.
                    method_spec = replace(
                        method_spec,
                        name=operation_id,
                        validator=validate_document_invariants,
                    )
                if not generated_operation and not settings.get(
                    "allow_unsafe_mutating_execute_code", False
                ):
                    return {
                        "success": False,
                        "error_code": "unsafe_mutating_execute_code_disabled",
                        "error": (
                            "Arbitrary mutating execute_code is disabled in document "
                            "lease enforce mode. Use a typed MCP operation or explicitly "
                            "enable allow_unsafe_mutating_execute_code."
                        ),
                    }
                if not options.get("document"):
                    return {
                        "success": False,
                        "error_code": "document_not_locked",
                        "error": (
                            "execute_code mutations require options.document "
                            "(explicit document identity) and an owned lease. "
                            "Call acquire_document_lock first."
                        ),
                    }
                primary = options["document"]
                additional = list(options.get("affected_documents") or [])
                additional = [name for name in additional if name != primary]
                referenced = extract_referenced_documents_from_code(code)
                declared = {primary, *additional}
                if not generated_operation:
                    scope_validation = validate_unsafe_execute_scope(code, declared)
                    if not scope_validation["ok"]:
                        return {
                            "success": False,
                            "error_code": "UNSAFE_EXECUTE_SCOPE_REJECTED",
                            "error": (
                                "Unsafe live Python contains document access that "
                                "cannot be proven to match its declared lease scope"
                            ),
                            "violations": scope_validation["violations"],
                        }
                undeclared = referenced - declared
                if undeclared:
                    return {
                        "success": False,
                        "error_code": "multi_document_undeclared",
                        "error": (
                            "execute_code references documents not declared in "
                            f"options.document / affected_documents: {sorted(undeclared)}. "
                            "Declare and lock every affected document."
                        ),
                        "undeclared": sorted(undeclared),
                    }
                for name in declared:
                    allowed = authorize_document(name)
                    if not allowed.get("success"):
                        return allowed
                keys = []
                for name in declared:
                    try:
                        keys.append(resolve_doc_key(doc_name=name))
                    except Exception:
                        pass
                return self._call_with_mutation_context(
                    func,
                    params,
                    {
                        "request_id": dl.get_request_identity().get("request_id")
                        or str(uuid.uuid4()),
                        "method": method_spec.name,
                        "doc_keys": tuple(keys),
                        "doc_names": tuple(declared),
                        "identity": dict(dl.get_request_identity()),
                        "method_spec": method_spec,
                    },
                )

            # Public arbitrary read-only code must never execute against the
            # live GUI document.  Force the existing snapshot-worker path even
            # if a caller asks for execution_mode='gui'.
            safe_options = dict(options)
            safe_options["execution_mode"] = "worker"
            if len(params) > 1:
                params = (params[0], safe_options, *params[2:])
            else:
                params = (params[0], safe_options)

            # read_only: annotate if another instance owns the target
            result = func(*params)
            if options.get("document"):
                try:
                    key = resolve_doc_key(doc_name=options["document"])
                    return annotate_read_result(result, key)
                except Exception:
                    return result
            return result

        if method == "execute_code_async":
            return {
                "success": False,
                "error_code": "document_not_locked",
                "error": (
                    "execute_code_async is blocked while document lock enforcement "
                    "is enabled (no explicit document / lease). Use execute_code "
                    "with options.document and an owned lease instead."
                ),
            }

        if method == "create_document":
            # Creating a brand-new document does not require a prior lease.
            return func(*params)

        if kind == VerbKind.LIFECYCLE:
            return func(*params)

        if kind == VerbKind.READ_ONLY:
            result = func(*params)
            if doc_name:
                try:
                    key = resolve_doc_key(doc_name=doc_name)
                    return annotate_read_result(result, key)
                except Exception:
                    return result
            return result

        # MUTATING
        if not doc_name:
            return {
                "success": False,
                "error_code": "document_not_locked",
                "error": (
                    f"{method} requires an explicit document identity and an owned "
                    "lease while document lock enforcement is enabled. "
                    "Call acquire_document_lock first."
                ),
            }
        try:
            doc_key = resolve_doc_key(doc_name=doc_name)
        except Exception as exc:
            return {
                "success": False,
                "error_code": "document_not_locked",
                "error": f"Cannot resolve document {doc_name!r}: {exc}",
            }
        allowed = authorize_document(doc_name)
        if not allowed.get("success"):
            return allowed

        return self._call_with_mutation_context(
            func,
            params,
            {
                "request_id": dl.get_request_identity().get("request_id")
                or str(uuid.uuid4()),
                "method": method,
                "doc_keys": (doc_key,),
                "doc_names": (doc_name,),
                "identity": dict(dl.get_request_identity()),
                "method_spec": method_spec,
            },
        )

    def _dispatch_gui(self, task, timeout=None):
        """Run *task* on the GUI thread and preserve legacy string errors."""
        dispatcher = gui_dispatcher
        if dispatcher is None:
            return "RPC GUI dispatcher is not initialized"
        t = timeout if timeout is not None else self.TIMEOUT
        context = getattr(self._mutation_context, "value", None)
        inflight = self._current_inflight()
        request_id = inflight.request_id if inflight is not None else None
        if context:
            captured = {
                "request_id": context["request_id"],
                "method": context["method"],
                "doc_keys": tuple(context["doc_keys"]),
                "doc_names": tuple(context["doc_names"]),
                "identity": dict(context["identity"]),
                "method_spec": context["method_spec"],
            }
            request_id = captured["request_id"]
            original_task = task

            def task():
                dl = _import_document_lock()
                if inflight is not None:
                    inflight.token.checkpoint("gui_revalidation")
                if document_lease_service is not None:
                    lease = _import_document_lease()
                    credentials = []
                    marker_keys = list(captured["doc_keys"]) + list(
                        captured["doc_names"]
                    )
                    attribution_started = False
                    try:
                        for name in captured["doc_names"]:
                            credential, document_identity = _credential_for_document(
                                name, captured["identity"]
                            )
                            allowed_states = {lease.LeaseState.LOCKED_IDLE}
                            if captured["method_spec"].allowed_during_recovery:
                                allowed_states.add(lease.LeaseState.LOCKED_ERROR)
                            record = document_lease_service.authorize(
                                credential,
                                selector={
                                    "document_session_uuid": (
                                        document_identity.session_uuid
                                    ),
                                    "document_name": name,
                                },
                                allowed_states=allowed_states,
                            )
                            self._touch_inflight_credential(credential, inflight)
                            credentials.append((name, credential, record.state))
                            marker_keys.extend(
                                value
                                for value in (
                                    getattr(
                                        credential, "document_session_uuid", None
                                    ),
                                    getattr(record.document, "canonical_path", None),
                                    getattr(record.document, "comparison_key", None),
                                )
                                if value
                            )
                            _assert_mutation_file_metadata_unchanged(record)

                        operation = captured["method"]
                        if inflight is not None:
                            inflight.token.begin_mutation(
                                "gui_mutation_authorized"
                            )
                        for _name, credential, initial_state in credentials:
                            if "recompute" in operation:
                                document_lease_service.begin_recompute(credential)
                            elif initial_state == lease.LeaseState.LOCKED_ERROR:
                                document_lease_service.begin_recovery(
                                    credential, operation=operation
                                )
                            else:
                                document_lease_service.begin_mutation(
                                    credential, operation=operation
                                )
                        marker_keys = tuple(sorted(set(marker_keys)))
                        dl.begin_agent_mutation_scope(
                            captured["request_id"], marker_keys
                        )
                        attribution_started = True
                        documents = [
                            FreeCAD.getDocument(name)
                            for name, _credential, _state in credentials
                        ]
                        if any(document is None for document in documents):
                            raise RuntimeError(
                                "A declared document closed before mutation execution"
                            )
                        spec = captured["method_spec"]
                        try:
                            from document_lease import core_authority

                            generations = {
                                name: int(getattr(credential, "generation", 0) or 0)
                                for name, credential, _state in credentials
                            }
                            kind_names = core_authority.kinds_for_rpc_method(
                                captured["method"],
                                getattr(spec.kind, "value", str(spec.kind)),
                            )
                            capability_cm = (
                                core_authority.open_documents_mutation_capability(
                                    documents,
                                    generations=generations,
                                    kinds=kind_names,
                                )
                            )
                        except Exception:
                            from contextlib import nullcontext

                            capability_cm = nullcontext([])

                        with capability_cm:
                            with GuiMutationTransaction(
                                documents,
                                f"MCP: {operation}",
                                enabled=spec.transaction,
                            ) as transaction:
                                if inflight is not None:
                                    inflight.token.checkpoint("gui_mutation_invocation")
                                result = original_task()
                                failed = isinstance(result, dict) and (
                                    result.get("success") is False
                                    or result.get("ok") is False
                                )
                                if failed:
                                    transaction.abort()
                                elif spec.recompute:
                                    if inflight is not None:
                                        inflight.token.checkpoint("gui_recompute")
                                    for _name, credential, _state in credentials:
                                        document_lease_service.begin_recompute(
                                            credential
                                        )
                                    for document in documents:
                                        document.recompute()
                                if not failed and spec.validator is not None:
                                    validations = [
                                        spec.validator(document)
                                        for document in documents
                                    ]
                                    if isinstance(result, dict):
                                        result = dict(result)
                                        result["lease_postflight"] = validations
                        for name, credential, _state in credentials:
                            document = FreeCAD.getDocument(name)
                            dirty = (
                                require_document_modified(document)
                                if document is not None
                                else True
                            )
                            if failed:
                                document_lease_service.record_error(
                                    credential,
                                    code="OPERATION_FAILED",
                                    message=_redact_rpc_diagnostic(
                                        result.get("error")
                                        or result.get("message")
                                        or operation,
                                        identity=captured["identity"],
                                        inflight=inflight,
                                    ),
                                    request_id=captured["request_id"],
                                    dirty=dirty,
                                )
                            else:
                                document_lease_service.complete_operation(
                                    credential, dirty=dirty
                                )
                        return result
                    except Exception as exc:
                        for name, credential, _state in credentials:
                            try:
                                document = FreeCAD.getDocument(name)
                                document_lease_service.record_error(
                                    credential,
                                    code=getattr(
                                        exc,
                                        "code",
                                        type(exc).__name__.upper(),
                                    ),
                                    message=_redact_rpc_diagnostic(
                                        exc,
                                        identity=captured["identity"],
                                        inflight=inflight,
                                    ),
                                    request_id=captured["request_id"],
                                    dirty=(
                                        document_modified_or_dirty(document)
                                        if document is not None
                                        else True
                                    ),
                                )
                            except Exception:
                                pass
                        raise
                    finally:
                        if attribution_started:
                            dl.end_agent_mutation_scope(
                                captured["request_id"], marker_keys
                            )

                for key in captured["doc_keys"]:
                    allowed = dl.check_mutation_allowed(
                        key, identity=captured["identity"]
                    )
                    if not allowed.get("success"):
                        return allowed

                marker_keys = list(captured["doc_keys"]) + list(captured["doc_names"])
                marker_keys = tuple(sorted(set(marker_keys)))
                token = captured["identity"].get("lease_token") or ""
                operation = captured["method"]
                if inflight is not None:
                    inflight.token.begin_mutation("gui_mutation_authorized")
                started_state = (
                    dl.LeaseState.LOCKED_RECOMPUTING.value
                    if "recompute" in operation
                    else dl.LeaseState.LOCKED_EDITING.value
                )
                for key in captured["doc_keys"]:
                    transition = dl.transition_lease(
                        key,
                        token,
                        started_state,
                        current_operation=operation,
                        request_id=captured["request_id"],
                    )
                    if not transition.get("success"):
                        return transition
                dl.begin_agent_mutation_scope(captured["request_id"], marker_keys)
                try:
                    if inflight is not None:
                        inflight.token.checkpoint("gui_mutation_invocation")
                    result = original_task()
                    failed = isinstance(result, dict) and (
                        result.get("success") is False or result.get("ok") is False
                    )
                    dirty_by_name = {}
                    for name in captured["doc_names"]:
                        doc = FreeCAD.getDocument(name)
                        dirty_by_name[name] = (
                            document_modified_or_dirty(doc)
                            if doc is not None
                            else True
                        )
                    for index, key in enumerate(captured["doc_keys"]):
                        name = (
                            captured["doc_names"][index]
                            if index < len(captured["doc_names"])
                            else None
                        )
                        dl.transition_lease(
                            key,
                            token,
                            (
                                dl.LeaseState.LOCKED_ERROR.value
                                if failed
                                else dl.LeaseState.LOCKED_IDLE.value
                            ),
                            current_operation=(f"error:{operation}" if failed else ""),
                            document_dirty=dirty_by_name.get(name),
                            request_id=captured["request_id"],
                            error=(
                                {
                                    "code": "operation_failed",
                                    "message": str(
                                        result.get("error")
                                        or result.get("message")
                                        or operation
                                    ),
                                }
                                if failed
                                else None
                            ),
                        )
                    return result
                except Exception as exc:
                    for key in captured["doc_keys"]:
                        dl.transition_lease(
                            key,
                            token,
                            dl.LeaseState.LOCKED_ERROR.value,
                            current_operation=f"error:{operation}",
                            request_id=captured["request_id"],
                            error={
                                "code": type(exc).__name__,
                                "message": str(exc),
                            },
                        )
                    raise
                finally:
                    dl.end_agent_mutation_scope(
                        captured["request_id"], marker_keys
                    )

        replay_on_complete = None
        replay_cache = rpc_request_replay_cache
        completion_runtime_id = rpc_server_runtime_id
        if context and replay_cache is not None:
            session_id = context["identity"].get("authenticated_session_id")
            replay_runtime_id = context["identity"].get("instance_id")
            addon_request_id = context.get("request_id")
            replay_secrets = tuple(
                str(value)
                for value in (
                    context["identity"].get("rpc_session_token"),
                    *(
                        item.get("token")
                        for item in context["identity"].get(
                            "lease_credentials", ()
                        )
                        if isinstance(item, dict)
                    ),
                )
                if value
            )
            if session_id and replay_runtime_id and addon_request_id:

                def replay_on_complete(
                    completed_request_id, outcome, cancellation=None
                ):
                    result = outcome.value if outcome.ok else None
                    result_failed = isinstance(result, dict) and (
                        result.get("success") is False or result.get("ok") is False
                    )
                    response = {
                        "ok": bool(
                            outcome.ok
                            and not result_failed
                            and not (
                                cancellation
                                and cancellation.cancellation_requested
                            )
                        ),
                        "request_id": completed_request_id,
                        "addon_runtime_id": completion_runtime_id,
                        "late_completion": True,
                    }
                    if cancellation and cancellation.cancellation_requested:
                        response["error"] = {
                            "code": (
                                "REQUEST_CANCELLED_AFTER_MUTATION"
                                if cancellation.mutation_started
                                or cancellation.uncertain
                                else "REQUEST_CANCELLED"
                            ),
                            "message": "Authenticated request was cancelled",
                        }
                        response["cancellation"] = cancellation.to_public_dict()
                    elif outcome.ok:
                        response["result"] = result
                    else:
                        response["error"] = {
                            "code": "GUI_TASK_FAILED",
                            "message": outcome.error or "GUI task failed",
                        }
                    replay_cache.journal_completion(
                        replay_runtime_id,
                        completed_request_id,
                        response,
                        secrets=replay_secrets,
                    )

        completion_seen = threading.Event()
        session_id = inflight.session_id if inflight is not None else None
        gui_phase_registered = False
        if inflight is not None:
            rpc_inflight_request_registry.begin_gui_phase(
                inflight.session_id,
                inflight.request_id,
                f"gui:{context['method'] if context else 'lifecycle'}",
            )
            gui_phase_registered = True

        def on_complete(completed_request_id, outcome):
            completion_seen.set()
            completion_state = None
            if inflight is not None:
                completion_state = rpc_inflight_request_registry.end_gui_phase(
                    inflight.session_id, inflight.request_id
                )
                if (
                    completion_state is not None
                    and completion_state.cancellation_requested
                ):
                    self._complete_request_cancellation(
                        inflight,
                        dirty=(True if completion_state.mutation_started else None),
                    )
                    completion_state = (
                        rpc_inflight_request_registry.refresh_terminal(
                            inflight.session_id, inflight.request_id
                        )
                    )
            # A still-waiting handler publishes its response after this
            # callback returns.  Only a handler that already timed out needs
            # late-result journaling here.
            if replay_on_complete is not None and (
                completion_state is None or completion_state.handler_finished
            ):
                replay_on_complete(
                    completed_request_id, outcome, completion_state
                )

        try:
            return dispatcher.submit(
                task,
                t,
                request_id=request_id,
                session_id=session_id,
                on_complete=(
                    on_complete
                    if gui_phase_registered or replay_on_complete
                    else None
                ),
            )
        except GuiDispatchError as exc:
            if (
                gui_phase_registered
                and not completion_seen.is_set()
                and not (
                    isinstance(exc, GuiDispatchTimeout)
                    and "while executing" in str(exc)
                )
            ):
                rpc_inflight_request_registry.end_gui_phase(
                    inflight.session_id, inflight.request_id
                )
            logger.error("RPC GUI dispatch failed: %s", exc)
            if (
                context
                and document_lease_service is not None
                and isinstance(exc, GuiDispatchTimeout)
                and "before execution" not in str(exc)
            ):
                if inflight is not None:
                    inflight.token.mark_uncertain("gui_completion_uncertain")
                for name in context["doc_names"]:
                    try:
                        credential, _document_identity = _credential_for_document(
                            name, context["identity"]
                        )
                        document_lease_service.record_error(
                            credential,
                            code="GUI_COMPLETION_UNCERTAIN",
                            message=_redact_rpc_diagnostic(
                                exc, identity=context["identity"], inflight=inflight
                            ),
                            request_id=context["request_id"],
                            dirty=True,
                        )
                    except Exception:
                        pass
            if isinstance(exc, GuiDispatchTimeout):
                code = "GUI_TIMEOUT"
            elif isinstance(exc, GuiBusyAfterTimeout):
                code = "GUI_BUSY_AFTER_TIMEOUT"
            elif isinstance(exc, GuiTaskError):
                code = "GUI_TASK_FAILED"
            else:
                code = "GUI_DISPATCH_FAILED"
            return {
                "success": False,
                "error_code": code,
                "error": str(exc),
                "request_id": request_id,
                "completion_uncertain": bool(
                    isinstance(exc, GuiDispatchTimeout)
                    and "before execution" not in str(exc)
                ),
            }

    def _dispatch_snapshot_gui(self, task):
        """Snapshot saveCopy has no safe hard timeout; wait outside Qt."""
        dispatcher = gui_dispatcher
        if dispatcher is None:
            return "RPC GUI dispatcher is not initialized"
        try:
            return dispatcher.submit(task, None)
        except GuiDispatchError as exc:
            logger.error("RPC snapshot dispatch failed: %s", exc)
            return str(exc)

    def handshake_v2(self, payload):
        """Authenticate one exact MCP runtime before any lease operation."""
        if rpc_session_manager is None:
            return {
                "ok": False,
                "error": {
                    "code": "LEASE_PROTOCOL_UNAVAILABLE",
                    "message": "Authenticated RPC v2 is not configured for this profile",
                },
            }
        try:
            return rpc_session_manager.perform_handshake(payload)
        except Exception as exc:
            return lease_protocol_public_error(exc)

    @staticmethod
    def _ordered_envelope_params(method, params):
        """Bind named envelope params to the legacy positional RPC methods."""
        signature = inspect.signature(method)
        bound = signature.bind(**dict(params))
        bound.apply_defaults()
        ordered = []
        for parameter in signature.parameters.values():
            if parameter.name == "self":
                continue
            if parameter.kind in {
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            }:
                ordered.append(bound.arguments[parameter.name])
            elif parameter.kind == inspect.Parameter.VAR_POSITIONAL:
                ordered.extend(bound.arguments.get(parameter.name, ()))
            elif parameter.kind == inspect.Parameter.KEYWORD_ONLY:
                raise LeaseProtocolError(
                    "INVALID_METHOD_PARAMS",
                    "Authenticated RPC target has unsupported keyword-only parameters",
                )
            elif parameter.kind == inspect.Parameter.VAR_KEYWORD:
                if bound.arguments.get(parameter.name):
                    raise LeaseProtocolError(
                        "INVALID_METHOD_PARAMS",
                        "Authenticated RPC target does not accept arbitrary fields",
                    )
        return tuple(ordered)

    def invoke_v2(self, payload):
        """Authenticate, de-duplicate, and dispatch one immutable RPC envelope."""
        request_id = payload.get("request_id") if isinstance(payload, dict) else None
        session_manager = rpc_session_manager
        replay_cache = rpc_request_replay_cache
        invocation_runtime_id = rpc_server_runtime_id
        lease_service = document_lease_service
        if session_manager is None or replay_cache is None:
            return lease_protocol_public_error(
                LeaseProtocolError(
                    "LEASE_PROTOCOL_UNAVAILABLE",
                    "Authenticated RPC v2 is not configured for this profile",
                ),
                request_id=request_id,
            )
        dl = _import_document_lock()
        transport_identity = dl.get_request_identity()
        try:
            session, envelope = session_manager.authenticate_envelope(
                payload,
                transport_mcp_runtime_id=transport_identity.get("instance_id"),
            )
            forbidden = {
                "handshake_v2",
                "invoke_v2",
                "invoke_v2_control",
                "shutdown_rpc_server",
                "force_release_stale_lock",
            }
            if envelope.method in forbidden or envelope.method.startswith("_"):
                raise LeaseProtocolError(
                    "METHOD_NOT_ALLOWED",
                    "The requested method is not available through invoke_v2",
                )
            target = getattr(self, envelope.method, None)
            if target is None or not callable(target):
                raise LeaseProtocolError(
                    "UNKNOWN_METHOD", "The requested RPC method is not registered"
                )
            _validate_generated_operation_envelope(envelope)
            request_kind, _request_extractor = dl.classify_verb(envelope.method)
            method_spec = make_method_spec(envelope.method, request_kind.value)
            lease_affecting = method_spec.pin_replay_for_lease_lifetime
            if envelope.method == "execute_code":
                options = envelope.params.get("options")
                if isinstance(options, dict) and options.get("read_only") is True:
                    lease_affecting = False
            replay = replay_cache.claim(
                session.mcp.runtime_id,
                envelope,
                pin_to_owner_leases=lease_affecting,
            )
            if replay.status == "completed":
                return replay.response
            if replay.status == "in_progress":
                return {
                    "ok": False,
                    "request_id": envelope.request_id,
                    "addon_runtime_id": invocation_runtime_id,
                    "error": {
                        "code": "REQUEST_IN_PROGRESS",
                        "message": "The matching authenticated request is still running",
                    },
                }

            try:
                params = self._ordered_envelope_params(target, envelope.params)
                inflight = rpc_inflight_request_registry.register(
                    session.session_id,
                    envelope.request_id,
                    envelope.method,
                    (
                        InflightLeaseCredential(
                            lease_id=item.lease_id,
                            document_session_uuid=item.document_session_uuid,
                            generation=item.generation,
                            token=item.token,
                            mcp_instance_id=session.mcp.runtime_id,
                        )
                        for item in envelope.lease_credentials
                    ),
                    lease_affecting=lease_affecting,
                )
            except Exception:
                # Parameter binding and inflight registration precede dispatch,
                # so no document or lease side effect can have begun yet.
                replay_cache.abandon(session.mcp.runtime_id, envelope)
                raise
            previous_identity = dl.get_request_identity()
            dl.set_request_identity(
                instance_id=session.mcp.runtime_id,
                client=session.mcp.client_build_id,
                pid=session.mcp.pid,
                host=session.mcp.hostname,
                lease_token=None,
                rpc_port=transport_identity.get("rpc_port"),
                request_id=envelope.request_id,
                rpc_session_token=envelope.session_token,
                lease_credentials=[
                    {
                        "lease_id": item.lease_id,
                        "document_session_uuid": item.document_session_uuid,
                        "generation": item.generation,
                        "token": item.token,
                    }
                    for item in envelope.lease_credentials
                ],
                mcp_process_started_at=session.mcp.process_started_at,
                agent_id=(
                    envelope.operation.task_id
                    if envelope.operation and envelope.operation.task_id
                    else None
                ),
                authenticated_session_id=session.session_id,
            )
            self._inflight_context.value = inflight
            handler_status = "failed"
            response = None
            handler_finalized = False

            def finalize_response(
                outbound, cached, status, *, process_pinned=False
            ):
                """Close the cancellation gate before publishing replay state."""

                nonlocal handler_status, handler_finalized
                terminal_check = rpc_inflight_request_registry.finish_handler(
                    session.session_id,
                    envelope.request_id,
                    status=status,
                )
                if terminal_check is not None and terminal_check.cancellation_requested:
                    process_pinned = bool(
                        process_pinned
                        or terminal_check.mutation_started
                        or terminal_check.uncertain
                    )
                    resolution = (
                        inflight.token.cancellation_resolution()
                        if terminal_check.cancellation_resolved
                        else self._complete_request_cancellation(
                            inflight,
                            dirty=(
                                True
                                if terminal_check.mutation_started
                                or terminal_check.uncertain
                                else None
                            ),
                        )
                    )
                    cancellation_response = {
                        "ok": False,
                        "request_id": envelope.request_id,
                        "addon_runtime_id": invocation_runtime_id,
                        "result": {
                            "success": False,
                            "error_code": (
                                "REQUEST_CANCELLED_AFTER_MUTATION"
                                if terminal_check.mutation_started
                                or terminal_check.uncertain
                                else "REQUEST_CANCELLED"
                            ),
                            "error": "Authenticated request was cancelled",
                            "cancellation": terminal_check.to_public_dict(),
                            "lease_resolution": resolution,
                        },
                    }
                    outbound.clear()
                    outbound.update(cancellation_response)
                    cached = cancellation_response
                    status = "cancelled"
                    rpc_inflight_request_registry.finish_handler(
                        session.session_id,
                        envelope.request_id,
                        status=status,
                    )
                replay_cache.complete(
                    session.mcp.runtime_id,
                    envelope,
                    cached,
                    process_pinned=process_pinned,
                )
                handler_status = status
                handler_finalized = True
                return outbound

            dispatch_started = False
            try:
                inflight.token.checkpoint("dispatch")
                dispatch_started = True
                result = self._dispatch(envelope.method, params)
                cancellation = inflight.token.snapshot()
                if cancellation.cancellation_requested:
                    resolution = self._complete_request_cancellation(
                        inflight,
                        dirty=(True if cancellation.mutation_started else None),
                    )
                    result = {
                        "success": False,
                        "error_code": (
                            "REQUEST_CANCELLED_AFTER_MUTATION"
                            if cancellation.mutation_started or cancellation.uncertain
                            else "REQUEST_CANCELLED"
                        ),
                        "error": "Authenticated request was cancelled",
                        "cancellation": cancellation.to_public_dict(),
                        "lease_resolution": resolution,
                    }
                response = {
                    "ok": not (
                        isinstance(result, dict)
                        and (
                            result.get("success") is False or result.get("ok") is False
                        )
                    ),
                    "request_id": envelope.request_id,
                    "addon_runtime_id": invocation_runtime_id,
                    "result": result,
                }
                if lease_service is not None:
                    response["leases"] = [
                        item
                        for item in lease_service.list_records()
                        if item.get("document", {}).get("session_uuid")
                        in {
                            credential.document_session_uuid
                            for credential in envelope.lease_credentials
                        }
                    ]
                cached_response = response
                if (
                    envelope.method
                    in {
                        "acquire_document_lock",
                        "create_document",
                    }
                    and response["ok"]
                    and isinstance(result, dict)
                    and result.get("credential")
                ):
                    # The addon never retains a replayable copy of the raw
                    # acquisition token.  A transport-lost acquisition is
                    # recovered through redacted status/local reconciliation,
                    # not by returning the secret a second time.
                    cached_response = {
                        "ok": False,
                        "request_id": envelope.request_id,
                        "addon_runtime_id": invocation_runtime_id,
                        "error": {
                            "code": "ACQUISITION_RESULT_NOT_REPLAYABLE",
                            "message": (
                                "This acquisition request already completed; "
                                "its one-time credential cannot be returned again"
                            ),
                        },
                    }
                handler_status = (
                    "cancelled"
                    if inflight.token.snapshot().cancellation_requested
                    else ("completed" if response["ok"] else "failed")
                )
                result_code = (
                    str(result.get("error_code") or result.get("code") or "")
                    if isinstance(result, dict)
                    else ""
                )
                process_pinned = bool(
                    lease_affecting
                    and (
                        cancellation.uncertain
                        or (
                            isinstance(result, dict)
                            and bool(result.get("completion_uncertain"))
                        )
                        or result_code
                        in {
                            "GUI_COMPLETION_UNCERTAIN",
                            "REQUEST_CANCELLED_AFTER_MUTATION",
                            "REQUEST_OUTCOME_UNCERTAIN",
                        }
                    )
                )
                return finalize_response(
                    response,
                    cached_response,
                    handler_status,
                    process_pinned=process_pinned,
                )
            except RequestCancellationError as exc:
                resolution = self._complete_request_cancellation(inflight)
                response = {
                    "ok": False,
                    "request_id": envelope.request_id,
                    "addon_runtime_id": invocation_runtime_id,
                    "result": {
                        "success": False,
                        "error_code": (
                            "REQUEST_CANCELLED_AFTER_MUTATION"
                            if exc.snapshot.mutation_started or exc.snapshot.uncertain
                            else "REQUEST_CANCELLED"
                        ),
                        "error": str(exc),
                        "cancellation": exc.snapshot.to_public_dict(),
                        "lease_resolution": resolution,
                    },
                }
                handler_status = "cancelled"
                return finalize_response(
                    response,
                    response,
                    handler_status,
                    process_pinned=bool(
                        lease_affecting
                        and (exc.snapshot.mutation_started or exc.snapshot.uncertain)
                    ),
                )
            except Exception:
                if dispatch_started and lease_affecting:
                    # Once a lease-affecting dispatch has entered the common
                    # boundary, an escaping exception cannot prove whether a
                    # document-side effect occurred.  Retain a process-lifetime
                    # tombstone instead of ever applying this request again.
                    uncertainty_response = {
                        "ok": False,
                        "request_id": envelope.request_id,
                        "addon_runtime_id": invocation_runtime_id,
                        "error": {
                            "code": "REQUEST_OUTCOME_UNCERTAIN",
                            "message": (
                                "The authenticated request outcome is uncertain; "
                                "the same request ID will not be dispatched again"
                            ),
                        },
                    }
                    handler_status = "uncertain"
                    return finalize_response(
                        uncertainty_response,
                        uncertainty_response,
                        handler_status,
                        process_pinned=True,
                    )
                replay_cache.abandon(session.mcp.runtime_id, envelope)
                raise
            finally:
                if not handler_finalized:
                    failed_terminal = rpc_inflight_request_registry.finish_handler(
                        session.session_id,
                        envelope.request_id,
                        status=handler_status,
                    )
                    if (
                        failed_terminal is not None
                        and failed_terminal.cancellation_requested
                        and not failed_terminal.cancellation_resolved
                    ):
                        self._complete_request_cancellation(
                            inflight,
                            dirty=(
                                True
                                if failed_terminal.mutation_started
                                or failed_terminal.uncertain
                                else None
                            ),
                        )
                        rpc_inflight_request_registry.finish_handler(
                            session.session_id,
                            envelope.request_id,
                            status="cancelled",
                        )
                if hasattr(self._inflight_context, "value"):
                    del self._inflight_context.value
                dl.set_request_identity(**previous_identity)
        except Exception as exc:
            return lease_protocol_public_error(exc, request_id=request_id)

    def lease_heartbeat_batch(self, leases, client_monotonic_ns=""):
        """Renew a batch on the reserved control lane; state remains server-owned."""
        if document_lease_service is None:
            return {
                "success": False,
                "error_code": "LEASE_PROTOCOL_UNAVAILABLE",
                "error": "Document lease v2 is not initialized",
            }
        identity = _import_document_lock().get_request_identity()
        results = []
        for item in leases if isinstance(leases, list) else []:
            session_uuid = (
                item.get("document_session_uuid") if isinstance(item, dict) else ""
            )
            try:
                credential = _credential_from_wire(item)
                status = document_lease_service.heartbeat(
                    credential,
                    current_operation=(
                        _redact_rpc_diagnostic(
                            item.get("current_operation"), identity=identity
                        )
                        or None
                    ),
                )
                status["success"] = True
                results.append(status)
            except Exception as exc:
                failed = _lease_service_error(
                    exc, request_id=identity.get("request_id")
                )
                failed["document_session_uuid"] = session_uuid
                failed["revoked"] = getattr(exc, "code", "") in {
                    "LEASE_AUTHORIZATION_FAILED",
                    "LEASE_STATE_FORBIDS_OPERATION",
                }
                results.append(failed)
        return {"success": True, "leases": results}

    def lease_reconcile(self, credential):
        if document_lease_service is None:
            return _lease_service_error(RuntimeError("lease service unavailable"))
        captured_identity = dict(_import_document_lock().get_request_identity())
        lease = _import_document_lease()
        phase: dict[str, Any] = {}
        inflight = self._current_inflight()
        self._request_checkpoint("lease_reconcile_start")

        def prepare_gui_phase():
            try:
                if inflight is not None:
                    inflight.token.checkpoint("lease_reconcile_prepare_gui")
                parsed = _credential_from_wire(credential, captured_identity)
                document, identity = _live_document_from_selector(
                    {"document_session_uuid": parsed.document_session_uuid}
                )
                record = document_lease_service.authorize(
                    parsed,
                    selector={"document_session_uuid": parsed.document_session_uuid},
                    allowed_states={lease.LeaseState.STALE},
                )
                live_identity = document_identity_service.inspect_registered_document(
                    parsed.document_session_uuid, document
                )
                if identity != record.document or live_identity != record.document:
                    raise lease.LiveDocumentValidationError(
                        "live document identity does not match the stale lease"
                    )
                if not record.document.canonical_path or record.baseline is None:
                    raise lease.LiveDocumentValidationError(
                        "stale reconciliation requires a saved verified baseline"
                    )
                if (
                    not record.validation_complete
                    or record.last_verified_save_revision
                    < record.last_mutation_revision
                ):
                    raise lease.LiveDocumentValidationError(
                        "stale reconciliation requires a baseline verified after "
                        "the final mutation"
                    )
                phase.update(
                    credential=parsed,
                    document=document,
                    identity=live_identity,
                    record=record,
                    baseline=record.baseline,
                    canonical_path=record.document.canonical_path,
                )
                return {"success": True}
            except Exception as exc:
                return _lease_service_error(
                    exc, request_id=captured_identity.get("request_id")
                )

        self._request_checkpoint("lease_reconcile_prepare_queue")
        prepared = self._dispatch_gui(prepare_gui_phase)
        if not isinstance(prepared, dict) or not prepared.get("success"):
            return prepared

        try:
            self._request_checkpoint("lease_reconcile_hash")
            # Full SHA-256 plus stat-before/stat-after capture can be expensive.
            # It intentionally runs on the XML-RPC handler thread between two
            # short GUI-thread authority checks.
            fresh_baseline = lease.capture_file_baseline(
                phase["canonical_path"],
                platform=document_identity_service.platform,
            )
            self._request_checkpoint("lease_reconcile_hash_complete")
        except RequestCancellationError:
            raise
        except Exception as exc:
            return _lease_service_error(
                lease.LiveDocumentValidationError(
                    f"unable to capture a stable reconciliation baseline: {exc}"
                ),
                request_id=captured_identity.get("request_id"),
            )

        def reconcile_gui_phase():
            try:
                if inflight is not None:
                    inflight.token.checkpoint("lease_reconcile_commit_gui")
                parsed = phase["credential"]
                document, identity = _live_document_from_selector(
                    {"document_session_uuid": parsed.document_session_uuid}
                )
                if document is not phase["document"]:
                    raise lease.LiveDocumentValidationError(
                        "live document proxy changed during stale reconciliation"
                    )
                record = document_lease_service.authorize(
                    parsed,
                    selector={"document_session_uuid": parsed.document_session_uuid},
                    allowed_states={lease.LeaseState.STALE},
                )
                if record != phase["record"]:
                    raise lease.CoordinationError(
                        "stale lease authority changed during baseline capture"
                    )
                live_identity = document_identity_service.inspect_registered_document(
                    parsed.document_session_uuid, document
                )
                if (
                    identity != phase["identity"]
                    or live_identity != phase["identity"]
                    or live_identity != record.document
                ):
                    raise lease.LiveDocumentValidationError(
                        "live document identity changed during baseline capture"
                    )
                # Close the ordinary hash-to-GUI race with an immediate stat
                # check. Deliberate same-user metadata forgery remains outside
                # the cooperative threat model.
                _assert_mutation_file_metadata_unchanged(record)
                baseline_matches = bool(
                    fresh_baseline == phase["baseline"]
                    and fresh_baseline == record.baseline
                )
                if not baseline_matches:
                    raise lease.LiveDocumentValidationError(
                        "fresh reconciliation baseline does not exactly match "
                        "the persisted accepted baseline"
                    )
                evidence = lease.LiveDocumentValidation(
                    document=live_identity,
                    document_modified=require_document_modified(document),
                    baseline=fresh_baseline,
                    baseline_validated=True,
                )
                self._touch_inflight_credential(parsed, inflight)
                if inflight is not None:
                    inflight.token.begin_irreversible(
                        "lease_reconcile_state_commit"
                    )
                return {
                    "success": True,
                    "lease": document_lease_service.reconcile_stale(
                        parsed, validation=evidence
                    ).to_public_dict(),
                }
            except Exception as exc:
                return _lease_service_error(
                    exc, request_id=captured_identity.get("request_id")
                )

        self._request_checkpoint("lease_reconcile_commit_queue")
        return self._dispatch_gui(reconcile_gui_phase)

    def get_request_status(self, request_id):
        identity = _import_document_lock().get_request_identity()
        session_id = identity.get("authenticated_session_id")
        mcp_runtime_id = identity.get("instance_id")
        if rpc_request_replay_cache is None or not session_id or not mcp_runtime_id:
            return {
                "success": False,
                "error_code": "AUTHENTICATED_SESSION_REQUIRED",
                "error": "Request status requires an authenticated MCP runtime",
            }
        try:
            status = rpc_request_replay_cache.status(mcp_runtime_id, request_id)
            # Cancellation remains intentionally scoped to the exact session.
            # After session refresh the replay state remains visible, while an
            # old session's inflight details are not disclosed or cancellable.
            inflight = rpc_inflight_request_registry.status(session_id, request_id)
            return {
                "success": True,
                "request_id": request_id,
                "state": (
                    inflight.terminal_status
                    if inflight is not None and inflight.terminal
                    else status.status
                ),
                "response": status.response,
                "inflight": (
                    inflight.to_public_dict() if inflight is not None else None
                ),
            }
        except Exception as exc:
            return lease_protocol_public_error(exc, request_id=request_id)

    def invoke_v2_control(self, payload):
        """Authenticated v2 entrypoint admitted only on the control lane."""

        method = payload.get("method") if isinstance(payload, dict) else None
        allowed = {
            "lease_heartbeat_batch",
            "lease_reconcile",
            "get_request_status",
            "cancel_request",
            "get_worker_status",
            "cancel_worker_job",
        }
        if method not in allowed:
            request_id = payload.get("request_id") if isinstance(payload, dict) else None
            return lease_protocol_public_error(
                LeaseProtocolError(
                    "METHOD_NOT_CONTROL",
                    "The requested method is not available on the control lane",
                ),
                request_id=request_id,
            )
        return self.invoke_v2(payload)

    def cancel_request(self, target_request_id):
        """Cancel one request owned by this authenticated RPC session.

        This is a reserved control-plane operation.  It is intentionally not
        registered as a FastMCP/model-facing tool.
        """

        identity = _import_document_lock().get_request_identity()
        session_id = identity.get("authenticated_session_id")
        if not session_id:
            return {
                "success": False,
                "error_code": "AUTHENTICATED_SESSION_REQUIRED",
                "error": "Request cancellation is scoped to an authenticated session",
            }
        cancellation = rpc_inflight_request_registry.request_cancel(
            session_id, target_request_id
        )
        if cancellation.status == "unknown":
            return {
                "success": False,
                "error_code": "REQUEST_NOT_FOUND",
                "error": "No cancellable request exists in this authenticated session",
            }
        if cancellation.status == "not_cancellable":
            return {
                "success": False,
                "error_code": "REQUEST_NOT_CANCELLABLE",
                "error": "The request has crossed an irreversible completion boundary",
                "target_request_id": str(target_request_id),
                "cancellation": cancellation.to_public_dict(),
            }
        target = rpc_inflight_request_registry.get(session_id, target_request_id)
        lease_events = []
        if target is not None and cancellation.status != "completed":
            target.token.set_phase("cancellation_requested")
            lease_events = self._begin_request_cancellation(target)

        queue_status = "not_queued"
        if target is not None and gui_dispatcher is not None:
            queue_status = gui_dispatcher.cancel_request(
                session_id, target_request_id
            )
        if target is not None and queue_status in {
            "cancelled_pending",
            "completed",
        }:
            target.token.set_phase(
                "cancelled_before_gui_execution"
                if queue_status == "cancelled_pending"
                else "cancelled_after_gui_phase"
            )
            lease_events = self._complete_request_cancellation(target)
        elif target is not None and cancellation.status in {
            "already_requested",
            "completed",
        }:
            cached = target.token.cancellation_resolution()
            if cached is not None:
                lease_events = cached

        return {
            "success": True,
            "target_request_id": str(target_request_id),
            "cancellation": cancellation.to_public_dict(),
            "gui_queue": queue_status,
            "lease_events": lease_events,
        }

    def ping(self):
        return True

    # --- Document lock verbs -------------------------------------------------

    def _acquire_document_lock_v2(
        self,
        requested_selector,
        *,
        request_identity,
        task_description,
        client,
        agent_id,
        hash_policy,
    ):
        """Reserve first, hash off Qt, then snapshot/promote on Qt."""

        request_id = request_identity.get("request_id")
        task_description = _redact_rpc_diagnostic(
            task_description, identity=request_identity
        )[:1024]
        client = _redact_rpc_diagnostic(client, identity=request_identity)[:256]
        agent_id = _redact_rpc_diagnostic(
            agent_id, identity=request_identity
        )[:256]
        if hash_policy != "sha256":
            return {
                "success": False,
                "error_code": "INVALID_HASH_POLICY",
                "error": "Only the sha256 acquisition baseline is supported",
            }
        if rpc_runtime_manifest is None:
            return {
                "success": False,
                "error_code": "LEASE_PROTOCOL_UNAVAILABLE",
                "error": "Authenticated runtime manifest is unavailable",
            }
        phase: dict[str, Any] = {}
        inflight = self._current_inflight()
        self._request_checkpoint("acquisition_start")

        def reserve_gui():
            reservation = None
            try:
                if inflight is not None:
                    inflight.token.checkpoint("acquisition_reserve_gui")
                document, document_identity = _live_document_from_selector(
                    requested_selector
                )
                if require_document_modified(document):
                    lease = _import_document_lease()
                    raise lease.DirtyAcquisitionError(
                        "a pre-existing dirty document requires local adoption"
                    )
                lease = _import_document_lease()
                owner = lease.LeaseOwner(
                    addon_profile_id=rpc_runtime_manifest.profile_id,
                    addon_runtime_id=rpc_runtime_manifest.addon_runtime_id,
                    freecad_pid=rpc_runtime_manifest.freecad_pid,
                    freecad_process_started_at=(
                        rpc_runtime_manifest.freecad_process_started_at
                    ),
                    boot_id=rpc_runtime_manifest.boot_id,
                    mcp_instance_id=request_identity.get("instance_id") or "",
                    mcp_pid=int(request_identity.get("pid") or 0),
                    mcp_process_started_at=(
                        request_identity.get("mcp_process_started_at")
                        or addon_loaded_at
                    ),
                    hostname=document_lease_service.local_runtime_identity.hostname,
                    client=client or request_identity.get("client") or "",
                    agent_id=agent_id or request_identity.get("agent_id") or "",
                )
                reservation = document_lease_service.begin_acquisition(
                    {
                        "document_session_uuid": document_identity.session_uuid,
                        "document_name": document_identity.name,
                        **(
                            {"canonical_path": document_identity.canonical_path}
                            if document_identity.canonical_path
                            else {}
                        ),
                    },
                    owner,
                    task_summary=task_description,
                    document_dirty=False,
                )
                self._retain_inflight_credential(reservation.credential)
                phase.update(
                    credential=reservation.credential,
                    document_identity=document_identity,
                    document_name=document_identity.name,
                    canonical_path=document_identity.canonical_path,
                )
                if inflight is not None:
                    inflight.token.checkpoint("acquisition_reserved")
                return {"success": True}
            except RequestCancellationError:
                self._complete_request_cancellation(inflight)
                raise
            except Exception as exc:
                if reservation is not None:
                    try:
                        document_lease_service.abort_acquisition(reservation.credential)
                    except Exception as rollback_exc:
                        return _lease_service_error(rollback_exc, request_id=request_id)
                return _lease_service_error(exc, request_id=request_id)

        self._request_checkpoint("acquisition_reserve_queue")
        reserved = self._dispatch_gui(reserve_gui, timeout=self.EXECUTE_TIMEOUT)
        if not isinstance(reserved, dict) or not reserved.get("success"):
            return reserved

        try:
            self._request_checkpoint("acquisition_hash")
            baseline = None
            path = phase["canonical_path"]
            if path:
                if not os.path.isfile(path):
                    raise _import_document_lease().LeaseServiceError(
                        "saved document path is missing or is not a regular file"
                    )
                baseline = _import_document_lease().capture_file_baseline(
                    path, platform=document_identity_service.platform
                )
            phase["baseline"] = baseline
            self._request_checkpoint("acquisition_hash_complete")
        except RequestCancellationError:
            self._complete_request_cancellation(inflight)
            raise
        except Exception as exc:
            failure = exc

            def rollback_gui():
                try:
                    document_lease_service.abort_acquisition(phase["credential"])
                    return _lease_service_error(failure, request_id=request_id)
                except Exception as rollback_exc:
                    return _lease_service_error(rollback_exc, request_id=request_id)

            return self._dispatch_gui(rollback_gui, timeout=self.EXECUTE_TIMEOUT)

        def snapshot_and_promote_gui():
            snapshot_id = None
            marker_keys = []
            attribution_started = False
            credential = phase["credential"]
            try:
                if inflight is not None:
                    inflight.token.checkpoint("acquisition_snapshot_gui")
                document = FreeCAD.getDocument(phase["document_name"])
                if document is None:
                    raise RuntimeError(
                        "document closed while acquisition was preparing"
                    )
                original_identity = phase["document_identity"]
                marker_keys = {
                    original_identity.name,
                    original_identity.session_uuid,
                    str(original_identity.canonical_path or ""),
                } - {""}
                dl = _import_document_lock()
                dl.begin_agent_mutation_scope(request_id, marker_keys)
                attribution_started = True
                lease = _import_document_lease()
                document_lease_service.authorize(
                    credential,
                    selector={"document_session_uuid": original_identity.session_uuid},
                    allowed_states={lease.LeaseState.ACQUIRING},
                )
                observed = document_identity_service.inspect_registered_document(
                    original_identity.session_uuid, document
                )
                if (
                    observed.comparison_key != original_identity.comparison_key
                    or observed.file_identity != original_identity.file_identity
                ):
                    raise lease.CoordinationError(
                        "live document identity changed during acquisition"
                    )
                if require_document_modified(document):
                    raise lease.DirtyAcquisitionError(
                        "document became dirty during acquisition"
                    )
                if inflight is not None:
                    inflight.token.begin_mutation("acquisition_snapshot_save_copy")
                snapshot_id = create_lease_baseline_snapshot_gui(document)
                if inflight is not None:
                    inflight.token.checkpoint("acquisition_snapshot_complete")
                if require_document_modified(document):
                    raise lease.DirtyAcquisitionError(
                        "document became dirty while its baseline snapshot was captured"
                    )
                grant = document_lease_service.complete_acquisition(
                    credential,
                    baseline=phase["baseline"],
                    baseline_validated=bool(original_identity.canonical_path),
                    snapshot_id=snapshot_id,
                )
                try:
                    from document_lease import core_authority

                    core_authority.sync_owner_from_lease_record(
                        document, grant.record
                    )
                except Exception:
                    FreeCAD.Console.PrintWarning(
                        "[MCP] core mutation owner sync failed after acquire\n"
                    )
                return {
                    "success": True,
                    **grant.to_dict(),
                    "expiry_policy": {
                        "heartbeat_interval_seconds": 10,
                        "sidecar_flush_interval_seconds": 30,
                        "stale_after_seconds": 90,
                    },
                }
            except RequestCancellationError:
                self._complete_request_cancellation(
                    inflight, dirty=True, snapshot_id=snapshot_id
                )
                raise
            except Exception as exc:
                try:
                    document_lease_service.abort_acquisition(credential)
                except Exception as rollback_exc:
                    # A failed CAS rollback is stricter than the triggering
                    # error. Keep both the sidecar and recovery artifact.
                    return _lease_service_error(rollback_exc, request_id=request_id)
                if snapshot_id:
                    discard_lease_baseline_snapshot(snapshot_id)
                return _lease_service_error(exc, request_id=request_id)
            finally:
                dl = _import_document_lock()
                if attribution_started:
                    dl.end_agent_mutation_scope(request_id, marker_keys)

        self._request_checkpoint("acquisition_snapshot_queue")
        return self._dispatch_gui(
            snapshot_and_promote_gui, timeout=self.EXECUTE_TIMEOUT
        )

    def acquire_document_lock(
        self,
        doc_name: str = "",
        file_path: str = "",
        session_id: str = "",
        task_description: str = "",
        client: str = "",
        selector: dict[str, Any] | None = None,
        agent_id: str = "",
        hash_policy: str = "sha256",
    ) -> dict[str, Any]:
        """Acquire an exclusive renewable write lease for a document."""
        try:
            dl = _import_document_lock()
        except ImportError as exc:
            return {"success": False, "error": str(exc)}
        if not dl.is_enabled():
            return {
                "success": False,
                "error_code": "document_lock_disabled",
                "error": "enable_document_lock is false in freecad_mcp_settings.json",
            }
        identity = dl.get_request_identity()
        instance_id = identity.get("instance_id") or ""
        if not instance_id:
            return {
                "success": False,
                "error_code": "missing_instance_id",
                "error": "X-MCP-Instance-Id header is required to acquire a lock",
            }
        if not (doc_name or file_path or session_id or selector):
            return {
                "success": False,
                "error_code": "document_identity_required",
                "error": (
                    "Provide an explicit doc_name, file_path, or session_id "
                    "(never implicitly locks ActiveDocument)"
                ),
            }

        if document_lease_service is not None and identity.get(
            "authenticated_session_id"
        ):
            requested_selector = dict(selector or {})
            if doc_name:
                requested_selector.setdefault("document_name", doc_name)
            if file_path:
                requested_selector.setdefault("canonical_path", file_path)
            if session_id:
                requested_selector.setdefault("document_session_uuid", session_id)
            return self._acquire_document_lock_v2(
                requested_selector,
                request_identity=identity,
                task_description=task_description,
                client=client,
                agent_id=agent_id,
                hash_policy=hash_policy,
            )

        def task():
            name = doc_name
            dirty = False
            if name:
                doc = FreeCAD.getDocument(name)
                if doc is None:
                    return {
                        "success": False,
                        "error_code": "document_not_found",
                        "error": f"Document {name!r} not found",
                    }
                dirty = document_modified_or_dirty(doc)
                fname = getattr(doc, "FileName", None) or ""
                path = file_path or (fname if fname else "")
            else:
                path = file_path
                name = doc_name or ""
            key = dl.resolve_doc_key(
                doc_name=name or None,
                file_path=path or None,
                session_id=session_id or None,
            )
            result = dl.acquire_lease(
                doc_key=key,
                doc_name=name or key,
                instance_id=instance_id,
                client=client or identity.get("client") or "",
                pid=int(identity.get("pid") or 0),
                host=identity.get("host") or "",
                task_description=task_description or "",
                rpc_port=identity.get("rpc_port"),
                document_dirty=dirty,
            )
            if result.get("success"):
                try:
                    from lock_indicator import refresh_lock_indicator

                    refresh_lock_indicator()
                except Exception:
                    pass
            return result

        return self._dispatch_gui(task)

    def get_document_lock(
        self,
        doc_name: str = "",
        file_path: str = "",
        session_id: str = "",
        selector: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            dl = _import_document_lock()
        except ImportError as exc:
            return {"success": False, "error": str(exc)}
        if not dl.is_enabled():
            return {
                "success": False,
                "error_code": "document_lock_disabled",
                "error": "enable_document_lock is false",
            }
        if not (doc_name or file_path or session_id or selector):
            return {
                "success": False,
                "error_code": "document_identity_required",
                "error": "Provide doc_name, file_path, or session_id",
            }
        if document_lease_service is not None:
            try:
                requested_selector = dict(selector or {})
                if doc_name:
                    requested_selector.setdefault("document_name", doc_name)
                if file_path:
                    requested_selector.setdefault("canonical_path", file_path)
                if session_id:
                    requested_selector.setdefault("document_session_uuid", session_id)
                _document, document_identity = _live_document_from_selector(
                    requested_selector
                )
                record = document_lease_service.get_effective(
                    {"document_session_uuid": document_identity.session_uuid}
                )
                if record is not None:
                    return {
                        "success": True,
                        "locked": True,
                        "source": record.get("source", "local"),
                        "lease": record,
                    }
                if document_identity.canonical_path:
                    lease = _import_document_lease()
                    sidecar = lease.sidecar_path_for(document_identity.canonical_path)
                    if os.path.lexists(sidecar):
                        try:
                            shadow = document_lease_service.sidecar_store.read(sidecar)
                            return {
                                "success": True,
                                "locked": True,
                                "source": "foreign_sidecar",
                                "lease": shadow.to_public_dict(),
                            }
                        except Exception as exc:
                            return {
                                "success": True,
                                "locked": True,
                                "source": "unknown_sidecar",
                                "error_code": "SIDECAR_UNKNOWN",
                                "error": str(exc)[:2048],
                            }
                return {
                    "success": True,
                    "locked": False,
                    "document": document_identity.to_dict(),
                    "lease": None,
                }
            except Exception as exc:
                return _lease_service_error(exc)
        try:
            key = dl.resolve_doc_key(
                doc_name=doc_name or None,
                file_path=file_path or None,
                session_id=session_id or None,
            )
        except Exception as exc:
            return {"success": False, "error": str(exc)}
        lease = dl.get_lease(key)
        if lease is None:
            return {"success": True, "locked": False, "doc_key": key, "lease": None}
        return {
            "success": True,
            "locked": True,
            "doc_key": key,
            "lease": lease.to_dict(),
        }

    def list_document_locks(self) -> dict[str, Any]:
        try:
            dl = _import_document_lock()
        except ImportError as exc:
            return {"success": False, "error": str(exc)}
        if not dl.is_enabled():
            return {
                "success": False,
                "error_code": "document_lock_disabled",
                "error": "enable_document_lock is false",
            }

        def task():
            if document_lease_service is not None:
                lease = _import_document_lease()
                local = document_lease_service.list_effective_records()
                local_ids = {
                    item.get("document", {}).get("session_uuid") for item in local
                }
                shadows = []
                for document in FreeCAD.listDocuments().values():
                    try:
                        document_identity = _ensure_v2_document(document)
                        if (
                            document_identity.session_uuid in local_ids
                            or not document_identity.canonical_path
                        ):
                            continue
                        sidecar = lease.sidecar_path_for(
                            document_identity.canonical_path
                        )
                        if not os.path.lexists(sidecar):
                            continue
                        try:
                            record = document_lease_service.sidecar_store.read(sidecar)
                            shadows.append(
                                {
                                    "source": "foreign_sidecar",
                                    "lease": record.to_public_dict(),
                                }
                            )
                        except Exception as exc:
                            shadows.append(
                                {
                                    "source": "unknown_sidecar",
                                    "document": document_identity.to_dict(),
                                    "error_code": "SIDECAR_UNKNOWN",
                                    "error": str(exc)[:2048],
                                }
                            )
                    except Exception as exc:
                        shadows.append(
                            {
                                "source": "identity_error",
                                "error_code": "DOCUMENT_IDENTITY_ERROR",
                                "error": str(exc)[:2048],
                            }
                        )
                return {
                    "success": True,
                    "leases": local,
                    "sidecars": shadows,
                }

            registry = [r.to_dict() for r in dl.list_leases()]
            paths = []
            for doc in FreeCAD.listDocuments().values():
                fname = getattr(doc, "FileName", None) or ""
                if fname:
                    paths.append(fname)
            discovered = [r.to_dict() for r in dl.discover_sidecar_leases(paths)]
            return {
                "success": True,
                "leases": registry,
                "sidecars": discovered,
            }

        return self._dispatch_gui(task)

    def heartbeat_document_lock(
        self,
        doc_key: str,
        token: str,
        current_operation: str = "",
        state: str = "",
        document_dirty: bool | None = None,
    ) -> dict[str, Any]:
        try:
            dl = _import_document_lock()
        except ImportError as exc:
            return {"success": False, "error": str(exc)}
        if not dl.is_enabled():
            return {
                "success": False,
                "error_code": "document_lock_disabled",
                "error": "enable_document_lock is false",
            }
        safe_current_operation = _redact_rpc_diagnostic(current_operation)
        if token:
            safe_current_operation = safe_current_operation.replace(
                str(token), "<redacted>"
            ).replace(
                "sha256:" + hashlib.sha256(str(token).encode("utf-8")).hexdigest(),
                "<redacted>",
            )
        result = dl.heartbeat_lease(
            doc_key,
            token,
            current_operation=safe_current_operation or None,
            state=state or None,
            document_dirty=document_dirty,
        )
        if result.get("success"):
            try:
                from lock_indicator import refresh_lock_indicator

                refresh_lock_indicator()
            except Exception:
                pass
        return result

    def update_document_lock(
        self,
        selector,
        task_description="",
        progress_detail="",
    ):
        """Update bounded diagnostics only; state and dirty flags are authoritative."""
        if document_lease_service is None:
            return {
                "success": False,
                "error_code": "LEASE_PROTOCOL_UNAVAILABLE",
                "error": "Document lease v2 is not initialized",
            }
        try:
            credential, _document_identity, _document = _credential_for_selector(
                selector
            )
            request_identity = _import_document_lock().get_request_identity()
            operation = _redact_rpc_diagnostic(
                progress_detail, identity=request_identity
            )[:512]
            task = _redact_rpc_diagnostic(
                task_description, identity=request_identity
            )[:1024]
            status = document_lease_service.update_metadata(
                credential,
                task_summary=task if task_description else None,
                current_operation=operation if progress_detail else None,
            )
            return {"success": True, "lease": status}
        except Exception as exc:
            return _lease_service_error(exc)

    def _run_typed_save(
        self,
        selector,
        *,
        mode,
        destination="",
        overwrite=False,
        expected_destination_sha256="",
        validation_profile="default",
        release=False,
    ):
        if document_lease_service is None or save_service is None:
            return {
                "success": False,
                "error_code": "LEASE_PROTOCOL_UNAVAILABLE",
                "error": "Typed save requires document lease v2",
            }
        captured_identity = dict(_import_document_lock().get_request_identity())
        request_id = captured_identity.get("request_id")
        phase: dict[str, Any] = {}
        inflight = self._current_inflight()
        self._request_checkpoint("save_lifecycle_start")

        def error_response(exc):
            if isinstance(exc, SaveServiceError):
                return {
                    "success": False,
                    "error_code": exc.code,
                    "error": str(exc),
                    "save_error": exc.to_dict(request_id=request_id),
                }
            return _lease_service_error(exc, request_id=request_id)

        def marker_keys_for(document, document_identity):
            candidates = {
                str(getattr(document, "Name", "") or ""),
                str(document_identity.name or ""),
                str(document_identity.session_uuid or ""),
                str(getattr(document, "FileName", "") or ""),
                str(document_identity.canonical_path or ""),
                str(destination or ""),
            }
            for candidate in tuple(candidates):
                if not candidate:
                    continue
                candidates.add(os.path.normcase(candidate))
                if os.path.isabs(candidate):
                    candidates.add(os.path.normcase(os.path.realpath(candidate)))
            return sorted(candidates - {""})

        def prepare_gui_phase():
            credential = None
            save_state_entered = False
            marker_keys = []
            attribution_started = False
            try:
                if inflight is not None:
                    inflight.token.checkpoint("save_prepare_gui")
                credential, document_identity, document = _credential_for_selector(
                    selector, captured_identity
                )
                phase.update(
                    credential=credential,
                    document_session_uuid=document_identity.session_uuid,
                    document_name=document_identity.name,
                    original_identity=document_identity,
                    validation_expectations=_saved_document_expectations(document),
                    source_path=(str(getattr(document, "FileName", "") or "") or None),
                )
                marker_keys = marker_keys_for(document, document_identity)
                dl = _import_document_lock()
                dl.begin_agent_mutation_scope(request_id, marker_keys)
                attribution_started = True
                lease = _import_document_lease()
                record = document_lease_service.authorize(
                    credential,
                    selector={
                        "document_session_uuid": document_identity.session_uuid,
                        "document_name": document_identity.name,
                    },
                    allowed_states={
                        lease.LeaseState.LOCKED_IDLE,
                        lease.LeaseState.LOCKED_ERROR,
                    },
                )
                self._touch_inflight_credential(credential, inflight)
                saving = document_lease_service.begin_save(credential)
                save_state_entered = True
                phase.update(
                    saving_state_revision=saving.state_revision,
                    saving_mutation_revision=saving.last_mutation_revision,
                    lease_baseline=record.baseline,
                )
                if mode == "save_as":
                    if not destination:
                        raise ValueError("Save As requires a destination")
                    document_lease_service.reserve_save_as(credential, destination)
                    phase["reserved"] = True
                elif mode != "save":
                    raise ValueError(f"Unsupported save mode: {mode}")
                return {"success": True}
            except RequestCancellationError:
                self._complete_request_cancellation(inflight)
                raise
            except Exception as exc:
                if credential is not None and save_state_entered:
                    # This phase has not called FreeCAD. Remove a destination
                    # reservation, if any, and return the source lease to idle.
                    try:
                        document_lease_service.cancel_save_before_mutation(credential)
                    except Exception as recovery_exc:
                        return error_response(recovery_exc)
                return error_response(exc)
            finally:
                dl = _import_document_lock()
                if attribution_started:
                    dl.end_agent_mutation_scope(request_id, marker_keys)

        self._request_checkpoint("save_prepare_queue")
        prepared = self._dispatch_gui(prepare_gui_phase, timeout=self.EXECUTE_TIMEOUT)
        if not isinstance(prepared, dict) or not prepared.get("success"):
            return prepared

        try:
            self._request_checkpoint("save_filesystem_preflight")
            # Full source/destination SHA-256 capture is deliberately outside
            # Qt. Save As already owns its conservative destination sidecar.
            if mode == "save":
                preflight = save_service.prepare_save(
                    phase["source_path"],
                    expected_baseline=phase["lease_baseline"],
                    expected_path=phase["original_identity"].canonical_path,
                    validation_profile=validation_profile,
                )
            else:
                preflight = save_service.prepare_save_as(
                    phase["source_path"],
                    destination,
                    source_baseline=phase["lease_baseline"],
                    overwrite=bool(overwrite),
                    expected_destination_sha256=(expected_destination_sha256 or None),
                    validation_profile=validation_profile,
                )
            phase["preflight"] = preflight
            self._request_checkpoint("save_filesystem_preflight_complete")
        except RequestCancellationError:
            self._complete_request_cancellation(inflight)
            raise
        except Exception as exc:
            failure = exc

            def preflight_error_gui():
                credential = phase["credential"]
                try:
                    # A destination conflict occurred without touching the
                    # document; remove the reservation and keep the source
                    # usable. A changed source baseline is coordination loss
                    # and remains visibly locked/error.
                    if (
                        isinstance(failure, SaveServiceError)
                        and failure.stage == "destination_preflight"
                    ):
                        document_lease_service.cancel_save_before_mutation(credential)
                    else:
                        document = FreeCAD.getDocument(phase["document_name"])
                        document_lease_service.record_error(
                            credential,
                            code=getattr(
                                failure,
                                "code",
                                type(failure).__name__.upper(),
                            ),
                            message=_redact_rpc_diagnostic(
                                failure,
                                identity=captured_identity,
                                inflight=inflight,
                            ),
                            request_id=request_id,
                            dirty=(
                                document_modified_or_dirty(document)
                                if document is not None
                                else True
                            ),
                        )
                except Exception:
                    pass
                return True

            self._dispatch_gui(preflight_error_gui, timeout=self.EXECUTE_TIMEOUT)
            return error_response(failure)

        def invoke_save_gui_phase():
            marker_keys = []
            attribution_started = False
            credential = phase["credential"]
            try:
                if inflight is not None:
                    inflight.token.checkpoint("save_gui_revalidation")
                document = FreeCAD.getDocument(phase["document_name"])
                if document is None:
                    raise RuntimeError("document closed before save invocation")
                original_identity = phase["original_identity"]
                marker_keys = marker_keys_for(document, original_identity)
                dl = _import_document_lock()
                dl.begin_agent_mutation_scope(request_id, marker_keys)
                attribution_started = True
                lease = _import_document_lease()
                record = document_lease_service.authorize(
                    credential,
                    selector={"document_session_uuid": phase["document_session_uuid"]},
                    allowed_states={lease.LeaseState.LOCKED_SAVING},
                )
                if (
                    record.state_revision != phase["saving_state_revision"]
                    or record.last_mutation_revision
                    != phase["saving_mutation_revision"]
                ):
                    raise lease.CoordinationError(
                        "lease changed during filesystem save preflight"
                    )
                live_identity = document_identity_service.inspect_registered_document(
                    phase["document_session_uuid"], document
                )
                if (
                    live_identity.comparison_key != original_identity.comparison_key
                    or live_identity.file_identity != original_identity.file_identity
                ):
                    raise lease.CoordinationError(
                        "live document identity changed before save invocation"
                    )
                if inflight is not None:
                    inflight.token.begin_mutation("save_invocation")
                try:
                    from document_lease import core_authority

                    save_kinds = core_authority.kinds_for_rpc_method(
                        "save_document_as" if mode == "save_as" else "save_document",
                        "save",
                    )
                    capability_cm = core_authority.open_mutation_capability(
                        document,
                        generation=int(getattr(credential, "generation", 0) or 0),
                        kinds=save_kinds,
                    )
                except Exception:
                    from contextlib import nullcontext

                    capability_cm = nullcontext(None)
                with capability_cm:
                    if mode == "save":
                        invocation = save_service.invoke_save_gui(
                            document, phase["preflight"]
                        )
                    else:
                        invocation = save_service.invoke_save_as_gui(
                            document, phase["preflight"]
                        )
                phase["invocation"] = invocation
                if inflight is not None:
                    inflight.token.checkpoint("save_invocation_complete")
                return {"success": True}
            except RequestCancellationError:
                self._complete_request_cancellation(
                    inflight,
                    dirty=(
                        True
                        if inflight is not None
                        and inflight.token.snapshot().mutation_started
                        else None
                    ),
                )
                raise
            except Exception as exc:
                try:
                    # A newly appeared/changed destination is a pre-write
                    # conflict. Source identity changes and all uncertain save
                    # outcomes must remain locked/error.
                    if (
                        isinstance(exc, SaveServiceError)
                        and exc.code == "SAVE_AS_DESTINATION_CONFLICT"
                        and not exc.mutation_may_have_occurred
                    ):
                        document_lease_service.cancel_save_before_mutation(credential)
                    else:
                        document = FreeCAD.getDocument(phase["document_name"])
                        document_lease_service.record_error(
                            credential,
                            code=getattr(exc, "code", type(exc).__name__.upper()),
                            message=_redact_rpc_diagnostic(
                                exc,
                                identity=captured_identity,
                                inflight=inflight,
                            ),
                            request_id=request_id,
                            dirty=(
                                document_modified_or_dirty(document)
                                if document is not None
                                else True
                            ),
                        )
                except Exception:
                    pass
                return error_response(exc)
            finally:
                dl = _import_document_lock()
                if attribution_started:
                    dl.end_agent_mutation_scope(request_id, marker_keys)

        self._request_checkpoint("save_invocation_queue")
        invoked = self._dispatch_gui(
            invoke_save_gui_phase, timeout=self.EXECUTE_TIMEOUT
        )
        if not isinstance(invoked, dict) or not invoked.get("success"):
            return invoked
        invocation = phase.get("invocation")
        if invocation is None:
            return {
                "success": False,
                "error_code": "SAVE_PHASE_RESULT_MISSING",
                "error": "GUI save completed without an invocation record",
            }

        def validate_in_worker(saved_path, profile):
            return _validate_saved_document_worker(
                saved_path,
                phase["document_name"],
                profile,
                phase["validation_expectations"],
            )

        try:
            self._request_checkpoint("save_reopen_verification")
            # Intentionally runs on the XML-RPC caller thread, never Qt.
            result = save_service.verify_saved_file(
                invocation, domain_validator=validate_in_worker
            )
            self._request_checkpoint("save_reopen_verification_complete")
        except RequestCancellationError:
            self._complete_request_cancellation(inflight, dirty=True)
            raise
        except Exception as exc:
            failure = exc

            def validation_error_gui():
                try:
                    credential = phase["credential"]
                    document = FreeCAD.getDocument(phase["document_name"])
                    document_lease_service.record_error(
                        credential,
                        code=getattr(failure, "code", type(failure).__name__.upper()),
                        message=_redact_rpc_diagnostic(
                            failure,
                            identity=captured_identity,
                            inflight=inflight,
                        ),
                        request_id=request_id,
                        dirty=(
                            document_modified_or_dirty(document)
                            if document is not None
                            else True
                        ),
                    )
                except Exception:
                    pass
                return True

            self._dispatch_gui(validation_error_gui, timeout=self.EXECUTE_TIMEOUT)
            return error_response(failure)

        def promote_gui_phase():
            marker_keys = []
            attribution_started = False
            credential = phase["credential"]
            try:
                if inflight is not None:
                    inflight.token.checkpoint("save_promotion_gui")
                document = FreeCAD.getDocument(phase["document_name"])
                if document is None:
                    raise RuntimeError("saved document closed before lease promotion")
                original_identity = phase["original_identity"]
                marker_keys = marker_keys_for(document, original_identity)
                dl = _import_document_lock()
                dl.begin_agent_mutation_scope(request_id, marker_keys)
                attribution_started = True
                lease = _import_document_lease()
                record = document_lease_service.authorize(
                    credential,
                    selector={"document_session_uuid": phase["document_session_uuid"]},
                    allowed_states={lease.LeaseState.LOCKED_SAVING},
                )
                if (
                    record.state_revision != phase["saving_state_revision"]
                    or record.last_mutation_revision
                    != phase["saving_mutation_revision"]
                ):
                    raise lease.CoordinationError(
                        "lease changed while the saved file was being validated"
                    )
                live_identity = document_identity_service.inspect_registered_document(
                    phase["document_session_uuid"], document
                )
                _canonical, saved_comparison = lease.canonicalize_path(
                    result.path, platform=document_identity_service.platform
                )
                if live_identity.comparison_key != saved_comparison:
                    raise lease.CoordinationError(
                        "live document path changed before save promotion"
                    )
                save_service.revalidate_saved_document_gui(document, result)
                if mode == "save_as":
                    verified = document_lease_service.commit_save_as(
                        credential,
                        destination=result.path,
                        baseline=result.baseline,
                    )
                else:
                    verified = document_lease_service.mark_save_verified(
                        credential, baseline=result.baseline
                    )
                response = {
                    "success": True,
                    "save": result.to_dict(),
                    "lease": verified.to_public_dict(),
                    "aliases": {
                        "document_session_uuid": (credential.document_session_uuid),
                        "canonical_path": result.path,
                        "previous_path": result.previous_path,
                    },
                }
                if release:
                    promoted_identity = (
                        document_identity_service.inspect_registered_document(
                            credential.document_session_uuid, document
                        )
                    )
                    evidence = lease.LiveDocumentValidation(
                        document=promoted_identity,
                        document_modified=require_document_modified(document),
                        baseline=result.baseline,
                        baseline_validated=True,
                    )
                    if inflight is not None:
                        inflight.token.begin_irreversible(
                            "finalize_release_sidecar_cas"
                        )
                    response["release"] = document_lease_service.release_clean(
                        credential, validation=evidence
                    )
                    _discard_terminal_snapshot(response["release"])
                    response["released"] = True
                return response
            except RequestCancellationError:
                self._complete_request_cancellation(inflight, dirty=True)
                raise
            except Exception as exc:
                try:
                    document = FreeCAD.getDocument(phase["document_name"])
                    document_lease_service.record_error(
                        credential,
                        code=getattr(exc, "code", type(exc).__name__.upper()),
                        message=_redact_rpc_diagnostic(
                            exc,
                            identity=captured_identity,
                            inflight=inflight,
                        ),
                        request_id=request_id,
                        dirty=(
                            document_modified_or_dirty(document)
                            if document is not None
                            else True
                        ),
                    )
                except Exception:
                    pass
                return error_response(exc)
            finally:
                dl = _import_document_lock()
                if attribution_started:
                    dl.end_agent_mutation_scope(request_id, marker_keys)

        self._request_checkpoint("save_promotion_queue")
        return self._dispatch_gui(promote_gui_phase, timeout=self.EXECUTE_TIMEOUT)

    def save_document(self, selector, validation_profile="default"):
        return self._run_typed_save(
            selector,
            mode="save",
            validation_profile=validation_profile,
        )

    def save_document_as(
        self,
        selector,
        destination,
        overwrite=False,
        expected_destination_sha256="",
        validation_profile="default",
    ):
        return self._run_typed_save(
            selector,
            mode="save_as",
            destination=destination,
            overwrite=overwrite,
            expected_destination_sha256=expected_destination_sha256,
            validation_profile=validation_profile,
        )

    def finalize_document_edit(
        self,
        selector,
        save_mode="save",
        destination="",
        overwrite=False,
        expected_destination_sha256="",
        validation_profile="default",
    ):
        normalized = str(save_mode).lower().replace("-", "_")
        if normalized not in {"save", "save_as", "saveas", "first_save"}:
            return {
                "success": False,
                "error_code": "INVALID_SAVE_MODE",
                "error": "save_mode must be save, save_as, or first_save",
            }
        return self._run_typed_save(
            selector,
            mode=(
                "save_as"
                if normalized in {"save_as", "saveas", "first_save"}
                else "save"
            ),
            destination=destination,
            overwrite=overwrite,
            expected_destination_sha256=expected_destination_sha256,
            validation_profile=validation_profile,
            release=True,
        )

    def release_document_lock(
        self,
        doc_key: str = "",
        token: str = "",
        selector: dict[str, Any] | None = None,
        disposition: str = "saved",
    ) -> dict[str, Any]:
        try:
            dl = _import_document_lock()
        except ImportError as exc:
            return {"success": False, "error": str(exc)}
        if not dl.is_enabled():
            return {
                "success": False,
                "error_code": "document_lock_disabled",
                "error": "enable_document_lock is false",
            }
        if document_lease_service is not None and selector is not None:
            captured_identity = dict(dl.get_request_identity())
            inflight = self._current_inflight()
            self._request_checkpoint("release_start")

            def task():
                try:
                    if inflight is not None:
                        inflight.token.checkpoint("release_gui_revalidation")
                    if disposition not in {"saved", "restored"}:
                        raise ValueError(
                            "Agents may release only a verified saved or restored document"
                        )
                    credential, document_identity, document = _credential_for_selector(
                        selector, captured_identity
                    )
                    lease = _import_document_lease()
                    record = document_lease_service.authorize(
                        credential,
                        selector={
                            "document_session_uuid": (document_identity.session_uuid)
                        },
                        allowed_states={lease.LeaseState.LOCKED_IDLE},
                    )
                    self._touch_inflight_credential(credential, inflight)
                    evidence = _live_validation_evidence(
                        document, document_identity, record
                    )
                    if inflight is not None:
                        inflight.token.begin_irreversible("release_sidecar_cas")
                    terminal = document_lease_service.release_clean(
                        credential, validation=evidence
                    )
                    try:
                        from document_lease import core_authority

                        core_authority.sync_clear_from_release(document)
                    except Exception:
                        FreeCAD.Console.PrintWarning(
                            "[MCP] core mutation owner clear failed after release\n"
                        )
                    _discard_terminal_snapshot(terminal)
                    return {"success": True, "lease": terminal}
                except Exception as exc:
                    return _lease_service_error(
                        exc, request_id=captured_identity.get("request_id")
                    )

            return self._dispatch_gui(task, timeout=self.EXECUTE_TIMEOUT)
        result = dl.release_lease(doc_key, token)
        if result.get("success"):
            try:
                from lock_indicator import refresh_lock_indicator

                refresh_lock_indicator()
            except Exception:
                pass
        return result

    def force_release_stale_lock(self, doc_key: str) -> dict[str, Any]:
        """Reject remote force release; recovery is a confirmed local GUI action.

        The method remains as a compatibility tombstone so an older client
        receives an explicit safe failure instead of an XML-RPC unknown-method
        fault.  In particular it must not become usable merely by switching a
        profile to observe/off mode.
        """
        del doc_key
        return {
            "success": False,
            "error_code": "LOCAL_RECOVERY_REQUIRED",
            "error": (
                "Stale or malformed lease recovery is available only from "
                "FreeCAD's local document-lock UI with explicit confirmation"
            ),
        }

    def get_instance_info(self):
        """Report this addon instance's identity (lightweight, no GUI dispatch).

        Lets a client confirm it reached the intended FreeCAD when several
        isolated instances listen on nearby ports. ``instance_id`` comes from the
        per-profile settings (empty on the default profile)."""
        try:
            settings = load_settings()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        try:
            profile_path = FreeCAD.getUserAppDataDir()
        except Exception:
            profile_path = None
        try:
            freecad_version = list(_freecad_version_parts())
        except Exception:
            freecad_version = []
        profile_id = (
            settings.get("profile_instance_id") or settings.get("instance_id", "") or ""
        )
        endpoint = rpc_server_actual_endpoint or {
            "host": settings.get("rpc_bind_host", "127.0.0.1"),
            "port": settings.get("rpc_port", 9875),
        }
        return {
            "ok": True,
            "instance_id": profile_id,
            "profile_instance_id": profile_id,
            "addon_runtime_id": rpc_server_runtime_id,
            "pid": os.getpid(),
            "freecad_process_started_at": (
                rpc_runtime_manifest.freecad_process_started_at
                if rpc_runtime_manifest is not None
                else _process_started_at()
            ),
            "boot_id": (
                rpc_runtime_manifest.boot_id
                if rpc_runtime_manifest is not None
                else _boot_identity()
            ),
            "addon_loaded_at": addon_loaded_at,
            "rpc_started_at": rpc_server_started_at,
            "host": endpoint.get("host"),
            "port": endpoint.get("port"),
            "actual_endpoint": endpoint,
            "profile_path": profile_path,
            "protocol_versions": [1, 2],
            "protocol_version": 2 if rpc_session_manager is not None else 1,
            "protocol_features": (
                list(rpc_runtime_manifest.features)
                if rpc_runtime_manifest is not None
                else []
            ),
            "addon_version": "0.1.20",
            "addon_build_id": "freecad-mcp-addon-0.1.20",
            "freecad_version": freecad_version,
            "profile_path_fingerprint": _profile_fingerprint(),
            "document_lease_mode": settings.get("document_lease_mode", "off"),
        }

    def check_rpc_sync(self, nonce):
        """Round-trip a nonce through the GUI queue to prove call correlation."""
        res = self._dispatch_gui(lambda: {"nonce": nonce})
        if not isinstance(res, dict) or res.get("nonce") != nonce:
            return {
                "success": False,
                "expected_nonce": nonce,
                "received": res,
            }
        return {"success": True, "nonce": nonce}

    def create_document(self, name="New_Document"):
        dl = _import_document_lock()
        identity = dl.get_request_identity()
        inflight = self._current_inflight()
        self._request_checkpoint("create_document_start")

        if document_lease_service is not None and identity.get(
            "authenticated_session_id"
        ):

            def create_and_lease():
                lease = _import_document_lease()
                if inflight is not None:
                    inflight.token.checkpoint("create_document_gui")
                if FreeCAD.getDocument(name) is not None:
                    return {
                        "success": False,
                        "error_code": "DOCUMENT_ALREADY_OPEN",
                        "error": f"Document {name!r} is already open",
                    }
                if rpc_runtime_manifest is None:
                    return {
                        "success": False,
                        "error_code": "LEASE_PROTOCOL_UNAVAILABLE",
                        "error": "Authenticated runtime manifest is unavailable",
                    }
                if inflight is not None:
                    inflight.token.begin_mutation("create_document_invocation")
                created = self._create_document_gui(name)
                if created is not True:
                    return {"success": False, "error": str(created)}
                document = FreeCAD.getDocument(name)
                snapshot_id = ""
                selector = None
                reservation = None
                marker_keys = []
                attribution_started = False
                try:
                    if document is None:
                        raise RuntimeError("FreeCAD did not publish the new document")
                    document_identity = _ensure_v2_document(document)
                    selector = {
                        "document_session_uuid": document_identity.session_uuid,
                        "document_name": document_identity.name,
                    }
                    marker_keys = [
                        document_identity.name,
                        document_identity.session_uuid,
                    ]
                    dl = _import_document_lock()
                    dl.begin_agent_mutation_scope(
                        identity.get("request_id"), marker_keys
                    )
                    attribution_started = True
                    owner = lease.LeaseOwner(
                        addon_profile_id=rpc_runtime_manifest.profile_id,
                        addon_runtime_id=rpc_runtime_manifest.addon_runtime_id,
                        freecad_pid=rpc_runtime_manifest.freecad_pid,
                        freecad_process_started_at=(
                            rpc_runtime_manifest.freecad_process_started_at
                        ),
                        boot_id=rpc_runtime_manifest.boot_id,
                        mcp_instance_id=identity.get("instance_id") or "",
                        mcp_pid=int(identity.get("pid") or 0),
                        mcp_process_started_at=(
                            identity.get("mcp_process_started_at") or addon_loaded_at
                        ),
                        hostname=(
                            document_lease_service.local_runtime_identity.hostname
                        ),
                        client=identity.get("client") or "",
                        agent_id=identity.get("agent_id") or "",
                    )
                    # Publish in-process ACQUIRING authority before saveCopy so
                    # observers and re-entrant GUI work never see a newly
                    # created document without its authenticated fence.
                    reservation = document_lease_service.begin_acquisition(
                        selector,
                        owner,
                        task_summary="Create new document",
                        document_dirty=False,
                    )
                    self._retain_inflight_credential(reservation.credential)
                    if inflight is not None:
                        inflight.token.checkpoint(
                            "create_document_snapshot_invocation"
                        )
                    snapshot_id = create_lease_baseline_snapshot_gui(document)
                    if inflight is not None:
                        inflight.token.checkpoint("create_document_snapshot_complete")
                    grant = document_lease_service.complete_acquisition(
                        reservation.credential,
                        baseline=None,
                        baseline_validated=False,
                        snapshot_id=snapshot_id,
                    )
                    try:
                        from document_lease import core_authority

                        core_authority.sync_owner_from_lease_record(
                            document, grant.record
                        )
                    except Exception:
                        FreeCAD.Console.PrintWarning(
                            "[MCP] core mutation owner sync failed after create\n"
                        )
                    return {
                        "success": True,
                        "document_name": name,
                        **grant.to_dict(),
                        "expiry_policy": {
                            "heartbeat_interval_seconds": 10,
                            "sidecar_flush_interval_seconds": 30,
                            "stale_after_seconds": 90,
                        },
                    }
                except RequestCancellationError:
                    self._complete_request_cancellation(
                        inflight, dirty=True, snapshot_id=snapshot_id
                    )
                    raise
                except Exception as exc:
                    if reservation is not None:
                        try:
                            document_lease_service.abort_acquisition(
                                reservation.credential
                            )
                        except Exception:
                            # A failed exact-CAS rollback intentionally keeps a
                            # local recovery record and the document open.
                            pass
                    retained = None
                    if selector is not None:
                        try:
                            retained = document_lease_service.get(selector)
                        except Exception:
                            retained = None
                    if retained is None:
                        if snapshot_id:
                            discard_lease_baseline_snapshot(snapshot_id)
                        try:
                            FreeCAD.closeDocument(name)
                        except Exception:
                            pass
                    return _lease_service_error(
                        exc, request_id=identity.get("request_id")
                    )
                finally:
                    dl = _import_document_lock()
                    if attribution_started:
                        dl.end_agent_mutation_scope(
                            identity.get("request_id"), marker_keys
                        )

            return self._dispatch_gui(create_and_lease)

        res = self._dispatch_gui(lambda: self._create_document_gui(name))
        if res is True:
            return {"success": True, "document_name": name}
        else:
            return {"success": False, "error": res}

    def create_object(self, doc_name, obj_data: dict[str, Any]):
        obj = Object(
            name=obj_data.get("Name", "New_Object"),
            type=obj_data["Type"],
            analysis=obj_data.get("Analysis", None),
            properties=obj_data.get("Properties", {}),
        )
        res = self._dispatch_gui(lambda: self._create_object_gui(doc_name, obj))
        if res is True:
            return {"success": True, "object_name": obj.name}
        else:
            return {"success": False, "error": res}

    def edit_object(
        self, doc_name: str, obj_name: str, properties: dict[str, Any]
    ) -> dict[str, Any]:
        obj = Object(
            name=obj_name,
            properties=properties.get("Properties", {}),
        )
        res = self._dispatch_gui(lambda: self._edit_object_gui(doc_name, obj))
        if res is True:
            return {"success": True, "object_name": obj.name}
        else:
            return {"success": False, "error": res}

    def inspect_references(
        self,
        doc_name: str,
        object_names: list[str] | None = None,
        only_invalid: bool = False,
        validate: bool = False,
    ) -> dict[str, Any]:
        """Inspect link properties without serializing shapes or recomputing."""
        res = self._dispatch_gui(
            lambda: inspect_references_gui(
                doc_name,
                object_names,
                only_invalid=bool(only_invalid),
                validate=bool(validate),
            )
        )
        if isinstance(res, dict):
            return res
        return {"ok": False, "error": str(res)}

    def repair_references(
        self,
        doc_name: str,
        repairs: list[dict[str, Any]],
        recompute: bool = False,
        validate: bool = False,
    ) -> dict[str, Any]:
        """Atomically rewrite link properties, deferring recompute by default."""
        res = self._dispatch_gui(
            lambda: repair_references_gui(
                doc_name,
                repairs,
                recompute=bool(recompute),
                validate=bool(validate),
            )
        )
        if isinstance(res, dict):
            return res
        return {"ok": False, "repair_committed": False, "error": str(res)}

    def delete_object(self, doc_name: str, obj_name: str):
        res = self._dispatch_gui(lambda: self._delete_object_gui(doc_name, obj_name))
        if res is True:
            return {"success": True, "object_name": obj_name}
        else:
            return {"success": False, "error": res}

    @staticmethod
    def _collect_invalid_objects() -> dict[str, list[dict[str, Any]]]:
        flagged: dict[str, list[dict[str, Any]]] = {}
        for doc_name, doc in FreeCAD.listDocuments().items():
            entries = []
            for obj in doc.Objects:
                try:
                    state = list(getattr(obj, "State", []))
                    if any(s in ("Invalid", "Error", "Touched") for s in state):
                        entries.append(
                            {
                                "name": obj.Name,
                                "label": getattr(obj, "Label", obj.Name),
                                "state": state,
                            }
                        )
                except Exception:
                    pass
            if entries:
                flagged[doc_name] = entries
        return flagged

    @staticmethod
    def _classify_recompute_errors(
        before: dict[str, list[dict[str, Any]]],
        after: dict[str, list[dict[str, Any]]],
        target_doc: str | None,
    ) -> dict[str, list[dict[str, Any]]]:
        def _key(doc: str, name: str) -> tuple[str, str]:
            return doc, name

        before_keys = {
            _key(doc, item["name"]) for doc, items in before.items() for item in items
        }
        target_errors: list[dict[str, Any]] = []
        pre_existing: list[dict[str, Any]] = []
        unrelated: list[dict[str, Any]] = []
        for doc, items in after.items():
            for item in items:
                entry = {
                    "document": doc,
                    "object": item["name"],
                    "state": item["state"],
                }
                key = _key(doc, item["name"])
                if target_doc and doc == target_doc:
                    if key in before_keys:
                        pre_existing.append(entry)
                    else:
                        target_errors.append(entry)
                else:
                    unrelated.append(entry)
        return {
            "target_recompute_errors": target_errors,
            "pre_existing_target_errors": pre_existing,
            "unrelated_document_errors": unrelated,
        }

    def execute_code(
        self, code: str, options: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not self.allow_execute_code:
            return {
                "success": False,
                "is_error": True,
                "error_code": "remote_execute_code_disabled",
                "error": "Arbitrary execute_code is disabled while remote RPC is enabled",
            }
        options = options or {}
        execution_mode = options.get("execution_mode", "auto")
        if execution_mode not in ("gui", "worker", "auto"):
            return {
                "success": False,
                "is_error": True,
                "error_code": "invalid_execution_mode",
                "error": f"Unsupported execution_mode: {execution_mode!r}",
            }
        # Arbitrary Python marked read-only is never evaluated against the live
        # GUI document.  The caller's execution-mode preference cannot weaken
        # this boundary: typed/audited GUI reads have their own RPC methods,
        # while public execute_code always receives an immutable worker snapshot.
        # This applies in off/observe mode as well as enforce mode so changing
        # compatibility mode cannot silently re-enable live "read-only" code.
        read_only_requested = bool(options.get("read_only", False))
        use_worker = execution_mode == "worker" or read_only_requested
        if use_worker:
            if not bool(options.get("read_only", False)):
                return {
                    "success": False,
                    "is_error": True,
                    "error_code": "invalid_execution_mode",
                    "error": "execution_mode='worker' requires read_only=True",
                }
            return self._execute_code_worker(code, options)

        if options.get("timeout_seconds") is not None:
            return {
                "success": False,
                "is_error": True,
                "error_code": "gui_timeout_not_supported",
                "error": (
                    "timeout_seconds is a hard worker timeout and cannot safely "
                    "stop code running on FreeCAD's GUI thread. Use read_only=true "
                    "with execution_mode='auto' or 'worker', or remove "
                    "timeout_seconds for bounded GUI work."
                ),
            }

        loop_risk = find_gui_geometry_loop_risk(code)
        read_only = bool(options.get("read_only", False))
        allow_gui_loop = bool(options.get("allow_gui_geometry_loop", False))
        block_unmarked_mutation = execution_mode == "auto" and not read_only
        block_forced_gui_analysis = execution_mode == "gui" and read_only
        # An expensive-geometry loop explicitly forced onto the GUI thread
        # (execution_mode='gui', read_only=false) is non-interruptible and froze
        # FreeCAD in the past.  It is now blocked unless the caller opts in with an
        # explicit allow_gui_geometry_loop=true, which is reserved for a genuine,
        # bounded live-document mutation that cannot run against a worker snapshot.
        block_forced_gui_loop = (
            execution_mode == "gui" and not read_only and not allow_gui_loop
        )
        # Point-in-solid sampling cannot be a necessary live-document mutation.
        # Keep it on the isolated worker even when a caller supplies the GUI
        # escape hatch intended for bounded modelling operations.
        block_worker_only_loop = (
            loop_risk is not None and loop_risk.worker_only_calls > 0
        )
        if loop_risk is not None and (
            block_unmarked_mutation
            or block_forced_gui_analysis
            or block_forced_gui_loop
            or block_worker_only_loop
        ):
            if block_worker_only_loop:
                guidance = (
                    "Worker-only geometry loops cannot use the GUI override. "
                    "Set read_only=true and execution_mode='worker' with a hard "
                    "timeout so they run in an isolated FreeCADCmd process."
                )
            elif block_forced_gui_analysis:
                guidance = (
                    "Read-only geometry loops cannot be forced onto the GUI thread. "
                    "Use execution_mode='auto' or 'worker' so the analysis runs in "
                    "an isolated FreeCADCmd process with a hard timeout."
                )
            elif block_forced_gui_loop:
                guidance = (
                    "An expensive-geometry loop on the GUI thread cannot be "
                    "interrupted and will freeze FreeCAD. For analysis, set "
                    "read_only=true and execution_mode='worker' with a hard timeout. "
                    "Only for a genuine bounded live-document mutation, pass "
                    "allow_gui_geometry_loop=true and split the work into small chunks."
                )
            else:
                guidance = (
                    "For analysis, set read_only=true and execution_mode='worker' "
                    "with a hard timeout. For an intentional document mutation, split "
                    "the work into bounded chunks and explicitly set "
                    "execution_mode='gui' with allow_gui_geometry_loop=true."
                )
            return {
                "success": False,
                "is_error": True,
                "blocked": "gui_thread_geometry_loop",
                "error": (
                    "Blocked before execution: "
                    f"{loop_risk.reason} ({loop_risk.expensive_calls} expensive "
                    f"geometry call sites, {loop_risk.loops} loops). {guidance}"
                ),
            }

        risk = find_gui_blocking_risk(
            code,
            read_only=bool(options.get("read_only", False)),
        )
        if risk is not None:
            return {
                "success": False,
                "is_error": True,
                "blocked": "gui_thread_boolean_audit",
                "error": (
                    "Blocked before execution: "
                    f"{risk.reason} ({risk.boolean_calls} boolean calls, "
                    f"{risk.transform_calls} transform calls). Use distToShape or "
                    "sampled point-to-shape distances, or run the boolean audit in "
                    "an isolated FreeCADCmd process."
                ),
            }

        def task():
            output_buffer = io.StringIO()
            opts = options
            target_doc = opts.get("document")
            recompute_mode = opts.get("recompute", "none")
            recompute_docs = opts.get("recompute_documents") or (
                [target_doc] if target_doc and recompute_mode == "target" else []
            )
            read_only = bool(opts.get("read_only", False))
            restore_active = bool(opts.get("restore_active_document", True))
            activate_doc = bool(opts.get("activate_document", False))

            active_before = (
                FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None
            )
            dirty_before = {
                name: require_document_modified(doc)
                for name, doc in FreeCAD.listDocuments().items()
            }
            invalid_before = self._collect_invalid_objects()

            if target_doc and activate_doc:
                doc = FreeCAD.getDocument(target_doc)
                if doc:
                    FreeCAD.setActiveDocument(target_doc)

            saved_hooks: list[tuple[Any, str, Any]] = []

            def _block_save(original):
                def _wrapped(*args, **kwargs):
                    raise RuntimeError("save blocked in read_only execute_code mode")

                return _wrapped

            # App.Document's save methods are C++ descriptors, so on some FreeCAD builds
            # they cannot be reassigned. Where the hook won't install, read_only degrades
            # to best-effort rather than failing the whole call; report which docs are
            # unguarded so the caller isn't misled into thinking saves are blocked.
            read_only_unguarded: list[str] = []
            if read_only:
                for doc_name, doc in FreeCAD.listDocuments().items():
                    for attr in ("save", "saveAs", "saveCopy"):
                        if hasattr(doc, attr):
                            original = getattr(doc, attr)
                            try:
                                setattr(doc, attr, _block_save(original))
                            except Exception:
                                if doc_name not in read_only_unguarded:
                                    read_only_unguarded.append(doc_name)
                                continue
                            saved_hooks.append((doc, attr, original))

            tb_info = None
            ok = False
            try:
                with contextlib.redirect_stdout(output_buffer):
                    exec(code, globals())
                ok = True
                FreeCAD.Console.PrintMessage("Python code executed successfully.\n")
            except Exception as exc:
                ok = False
                exc_type, exc_val, exc_tb = sys.exc_info()
                frames = traceback.extract_tb(exc_tb) if exc_tb else []
                last = frames[-1] if frames else None
                tb_info = {
                    "exception_type": exc_type.__name__ if exc_type else "Exception",
                    "message": str(exc_val),
                    "traceback": traceback.format_exc(),
                    "frames": [
                        {
                            "file": f.filename,
                            "line": f.lineno,
                            "function": f.name,
                            "code": f.line,
                        }
                        for f in frames
                    ],
                    "line_number": last.lineno if last else None,
                    "line_code": last.line if last else None,
                    "stdout": output_buffer.getvalue(),
                }
                FreeCAD.Console.PrintError(f"Error executing Python code: {exc}\n")
            finally:
                for doc, attr, original in saved_hooks:
                    try:
                        setattr(doc, attr, original)
                    except Exception:
                        pass

                if recompute_mode == "all":
                    for doc in FreeCAD.listDocuments().values():
                        try:
                            doc.recompute()
                        except Exception:
                            pass
                elif recompute_mode == "target" and recompute_docs:
                    for doc_name in recompute_docs:
                        doc = FreeCAD.getDocument(doc_name)
                        if doc:
                            try:
                                doc.recompute()
                            except Exception:
                                pass

                if restore_active and active_before:
                    try:
                        if FreeCAD.getDocument(active_before):
                            FreeCAD.setActiveDocument(active_before)
                    except Exception:
                        pass

            invalid_after = self._collect_invalid_objects()
            classified = self._classify_recompute_errors(
                invalid_before, invalid_after, target_doc
            )
            active_after = (
                FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None
            )
            dirty_after = {
                name: require_document_modified(doc)
                for name, doc in FreeCAD.listDocuments().items()
            }
            target_doc_obj = FreeCAD.getDocument(target_doc) if target_doc else None
            session = {
                "active_document_before": active_before,
                "active_document_after": active_after,
                "dirty_before": dirty_before,
                "dirty_after": dirty_after,
                "saved": False,
                "file_path": getattr(target_doc_obj, "FileName", "")
                if target_doc_obj
                else "",
                **classified,
            }
            if read_only_unguarded:
                session["read_only_unguarded_documents"] = read_only_unguarded
            if ok:
                return {
                    "ok": True,
                    "session": session,
                    "stdout": output_buffer.getvalue(),
                }
            return {
                "ok": False,
                "error": tb_info["message"] if tb_info else "Unknown error",
                "traceback": tb_info,
                "session": session,
                "stdout": output_buffer.getvalue(),
            }

        res = self._dispatch_gui(task, self.EXECUTE_TIMEOUT)
        if isinstance(res, str):
            return {"success": False, "error": res, "is_error": True}
        if res.get("ok"):
            session = res.get("session", {})
            flat_errors = []
            for key in (
                "target_recompute_errors",
                "pre_existing_target_errors",
                "unrelated_document_errors",
            ):
                for item in session.get(key, []):
                    flat_errors.append(
                        {
                            "doc": item.get("document")
                            or options.get("document")
                            or "?",
                            "name": item.get("object", "?"),
                            "state": item.get("state", []),
                        }
                    )
            return {
                "success": True,
                "message": "Python code execution completed.\nOutput: "
                + res.get("stdout", ""),
                "recompute_errors": flat_errors,
                "session": session,
                "structured": session,
                "execution": {"mode": "gui"},
            }
        tb = res.get("traceback")
        return {
            "success": False,
            "error": res.get("error", "Unknown error"),
            "traceback": tb,
            "structured": tb,
            "session": res.get("session", {}),
            "message": res.get("stdout", ""),
            "is_error": True,
        }

    def _execute_code_worker(
        self, code: str, options: dict[str, Any]
    ) -> dict[str, Any]:
        manager = worker_manager
        if manager is None:
            return {
                "success": False,
                "is_error": True,
                "error_code": "worker_unavailable",
                "error": "FreeCADCmd worker manager is not initialized",
            }
        try:
            workspace = manager.create_workspace()
        except Exception as exc:
            return {
                "success": False,
                "is_error": True,
                "error_code": "worker_unavailable",
                "error": str(exc),
            }

        snapshot = None
        with snapshot_coordinator:
            for attempt in range(2):
                snapshot = self._dispatch_snapshot_gui(
                    lambda: create_primary_snapshot_gui(
                        options.get("document"),
                        str(workspace),
                        link_policy=str(options.get("link_policy") or "strict"),
                    )
                )
                if not isinstance(snapshot, dict):
                    break
                if (
                    snapshot.get("error_code") != "snapshot_state_changed"
                    or attempt == 1
                ):
                    break
        if not isinstance(snapshot, dict) or not snapshot.get("ok"):
            import shutil

            shutil.rmtree(workspace, ignore_errors=True)
            if isinstance(snapshot, dict):
                return {
                    "success": False,
                    "is_error": True,
                    "error_code": snapshot.get("error_code", "snapshot_failed"),
                    "error": snapshot.get("error", "Snapshot creation failed"),
                }
            return {
                "success": False,
                "is_error": True,
                "error_code": "snapshot_failed",
                "error": str(snapshot),
            }
        return manager.execute(code, options, snapshot, workspace)

    def get_worker_status(self) -> dict[str, Any]:
        manager = worker_manager
        if manager is None:
            return {
                "available": False,
                "busy": False,
                "queue_depth": 0,
                "last_error": "Worker manager is not initialized",
            }
        return manager.status()

    def cancel_worker_job(self, job_id: str) -> dict[str, Any]:
        manager = worker_manager
        if manager is None:
            return {
                "success": False,
                "error_code": "worker_unavailable",
                "error": "Worker manager is not initialized",
            }
        return manager.cancel(job_id)

    def shutdown_rpc_server(self) -> dict[str, Any]:
        """Admit shutdown through the reserved control lane and respond first."""
        if shutdown_requested.is_set():
            return {"success": True, "state": "already_stopping"}
        shutdown_requested.set()
        timer = threading.Timer(0.05, stop_rpc_server)
        timer.name = "FreeCADMCP-RPC-Shutdown"
        timer.daemon = True
        timer.start()
        return {"success": True, "state": "stopping"}

    def get_objects(self, doc_name):
        # Must run in the GUI thread: serialize_object accesses ViewObject
        # and other GUI-backed properties that FreeCAD guards against
        # access from background threads.
        res = self._dispatch_gui(lambda: self._get_objects_gui(doc_name))
        if isinstance(res, list):
            return res
        return []

    def get_object(self, doc_name, obj_name):
        res = self._dispatch_gui(lambda: self._get_object_gui(doc_name, obj_name))
        # False sentinel means "not found"; timeout string → None
        if res is False or isinstance(res, str):
            return None
        return res

    def insert_part_from_library(self, doc_name, relative_path):
        res = self._dispatch_gui(
            lambda: self._insert_part_from_library(doc_name, relative_path)
        )
        if res is True:
            return {"success": True, "message": "Part inserted from library."}
        else:
            return {"success": False, "error": res}

    def list_documents(self):
        res = self._dispatch_gui(lambda: list(FreeCAD.listDocuments().keys()))
        return res if isinstance(res, list) else []

    def reload_document(self, doc_name: str) -> dict[str, Any]:
        res = self._dispatch_gui(lambda: self._reload_document_gui(doc_name))
        if res is True:
            return {"success": True, "document_name": doc_name}
        return {"success": False, "error": str(res)}

    def open_document(self, path: str) -> dict[str, Any]:
        from .gui_tools import open_document as _open_document

        def open_checked():
            existing_names = set(FreeCAD.listDocuments())
            if document_identity_service is not None:
                try:
                    document_identity_service.assert_open_path_available(path)
                except Exception as exc:
                    return {
                        "ok": False,
                        "success": False,
                        "error_code": "DUPLICATE_OR_INVALID_DOCUMENT_OPEN",
                        "error": _redact_rpc_diagnostic(exc),
                    }
            result = _open_document(path)
            if not isinstance(result, dict) or not result.get("ok"):
                return result
            document_name = str(result.get("document") or "")
            document = FreeCAD.getDocument(document_name)
            try:
                if document is None:
                    raise RuntimeError("opened document proxy is unavailable")
                identity = _ensure_v2_document(document)
                result["document_session_uuid"] = identity.session_uuid
                result["canonical_path"] = identity.canonical_path
                return result
            except Exception as exc:
                # The preflight prevents all known aliases. If the filesystem
                # or another GUI request raced it, do not leave the newly
                # created duplicate live after the post-open identity check.
                if document_name and document_name not in existing_names:
                    try:
                        FreeCAD.closeDocument(document_name)
                    except Exception:
                        logger.exception(
                            "Could not close a document rejected after open"
                        )
                return {
                    "ok": False,
                    "success": False,
                    "error_code": "DOCUMENT_OPEN_IDENTITY_REJECTED",
                    "error": _redact_rpc_diagnostic(exc),
                }

        res = self._dispatch_gui(open_checked)
        if isinstance(res, dict):
            return res
        return {"ok": False, "error": str(res)}

    def activate_document(self, doc_name: str) -> dict[str, Any]:
        from .gui_tools import activate_document as _activate_document

        res = self._dispatch_gui(lambda: _activate_document(doc_name))
        if isinstance(res, dict):
            return res
        return {"ok": False, "error": str(res)}

    def set_tree_expanded(
        self,
        doc_name: str,
        object_names: list | None = None,
        mode: str = "expand",
    ) -> dict[str, Any]:
        from .gui_tools import set_tree_expanded as _set_tree_expanded

        res = self._dispatch_gui(
            lambda: _set_tree_expanded(doc_name, object_names, mode)
        )
        if isinstance(res, dict):
            return res
        return {"ok": False, "error": str(res)}

    def select_subshapes(
        self,
        doc_name: str,
        selections: list | None = None,
        clear: bool = True,
    ) -> dict[str, Any]:
        from .gui_tools import select_subshapes as _select_subshapes

        res = self._dispatch_gui(
            lambda: _select_subshapes(doc_name, selections or [], clear)
        )
        if isinstance(res, dict):
            return res
        return {"ok": False, "error": str(res)}

    def get_selection(self) -> dict[str, Any]:
        from .gui_tools import get_selection as _get_selection

        res = self._dispatch_gui(_get_selection)
        if isinstance(res, dict):
            return res
        return {"ok": False, "error": str(res)}

    def get_gui_state(self) -> dict[str, Any]:
        from .gui_tools import get_gui_state as _get_gui_state

        res = self._dispatch_gui(_get_gui_state)
        if isinstance(res, dict):
            return res
        return {"ok": False, "error": str(res)}

    def recompute_and_wait(self, doc_name: str) -> dict[str, Any]:
        from .gui_tools import recompute_and_wait as _recompute_and_wait

        res = self._dispatch_gui(lambda: _recompute_and_wait(doc_name))
        if isinstance(res, dict):
            return res
        return {"ok": False, "error": str(res)}

    def set_section_view(
        self,
        enabled: bool | None = None,
        placement: dict | None = None,
        base: list | None = None,
        normal: list | None = None,
        no_manip: bool = True,
    ) -> dict[str, Any]:
        from .gui_tools import set_section_view as _set_section_view

        res = self._dispatch_gui(
            lambda: _set_section_view(
                enabled,
                placement=placement,
                base=base,
                normal=normal,
                no_manip=no_manip,
            )
        )
        if isinstance(res, dict):
            return res
        return {"ok": False, "error": str(res)}

    def run_fem_analysis(
        self, doc_name: str, analysis_name: str, timeout: int = 600
    ) -> dict[str, Any]:
        """Run the CalculiX solver on an existing Fem::FemAnalysis and return summary results."""
        try:
            timeout_s = int(timeout)
        except (TypeError, ValueError):
            return {"success": False, "error": f"invalid timeout: {timeout!r}"}
        res = self._dispatch_gui(
            lambda: self._run_fem_analysis_gui(doc_name, analysis_name),
            timeout=timeout_s,
        )
        if isinstance(res, dict):
            return res
        return {"success": False, "error": str(res)}

    def execute_code_async(self, code: str) -> dict[str, Any]:
        """Start code execution in a background thread and return immediately.

        Use for long-running OCCT operations (fuse/cut/loft) that would otherwise
        exceed the MCP timeout. The caller should poll a document object for
        completion status (e.g. check SessionState.Label via get_object).
        """

        def _set_status(msg):
            self._dispatch_gui(
                lambda: FreeCADGui.getMainWindow().statusBar().showMessage(msg)
            )

        def _clear_status():
            self._dispatch_gui(
                lambda: FreeCADGui.getMainWindow().statusBar().clearMessage()
            )

        def worker() -> None:
            # NOTE: we do NOT redirect sys.stdout here. contextlib.redirect_stdout
            # swaps stdout process-wide, not per-thread, so it would race with the
            # GUI thread and other concurrent work. Background code should report
            # via FreeCAD.Console (which is thread-safe) instead.
            try:
                exec(code, globals())
                FreeCAD.Console.PrintMessage("Async code execution completed.\n")
            except Exception as e:
                import traceback as _tb

                FreeCAD.Console.PrintError(f"Async code error: {e}\n{_tb.format_exc()}")
            finally:
                _clear_status()

        _set_status("MCP: running background task…")
        threading.Thread(target=worker, daemon=True).start()
        return {"success": True, "message": "Code execution started in background."}

    def get_parts_list(self):
        return get_parts_list()

    def get_active_screenshot(
        self,
        view_name: str | None = "Isometric",
        width: int | None = None,
        height: int | None = None,
        focus_object: str | None = None,
        focus_objects: list[str] | None = None,
        yaw_deg: float | None = None,
    ) -> str:
        """Get a screenshot of the active view.

        Returns a base64-encoded string of the screenshot or None if a screenshot
        cannot be captured (e.g., when in TechDraw or Spreadsheet view).
        """

        # First check if the active view supports screenshots
        def check_view_supports_screenshots():
            try:
                active_view = FreeCADGui.ActiveDocument.ActiveView
                if active_view is None:
                    FreeCAD.Console.PrintWarning("No active view available\n")
                    return False

                view_type = type(active_view).__name__
                has_save_image = hasattr(active_view, "saveImage")
                FreeCAD.Console.PrintMessage(
                    f"View type: {view_type}, Has saveImage: {has_save_image}\n"
                )
                return has_save_image
            except Exception as e:
                FreeCAD.Console.PrintError(f"Error checking view capabilities: {e}\n")
                return False

        supports_screenshots = self._dispatch_gui(check_view_supports_screenshots)

        if not supports_screenshots:
            logger.warning("Current view does not support screenshots")
            return None

        # If view supports screenshots, proceed with capture
        fd, tmp_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        res = self._dispatch_gui(
            lambda: save_active_screenshot(
                tmp_path,
                view_name or "Isometric",
                width,
                height,
                focus_object=focus_object,
                focus_objects=focus_objects,
                yaw_deg=yaw_deg,
            )
        )
        if res is True:
            try:
                with open(tmp_path, "rb") as image_file:
                    image_bytes = image_file.read()
                    encoded = base64.b64encode(image_bytes).decode("utf-8")
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            return encoded
        else:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            logger.warning("Failed to capture screenshot: %s", res)
            return None

    def capture_view_sequence(
        self,
        frames: list[dict[str, Any]] | None = None,
        width: int | None = None,
        height: int | None = None,
        orbit: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Capture multiple framed screenshots and return base64 PNG payloads."""

        def _run() -> dict[str, Any]:
            work_frames: list[dict[str, Any]] = []
            if orbit:
                work_frames.extend(
                    build_orbit_frames(
                        focus_objects=orbit.get("focus_objects"),
                        focus_object=orbit.get("focus_object"),
                        steps=int(orbit.get("steps") or 8),
                        view_name=str(orbit.get("view_name") or "Isometric"),
                        elevation_yaw_start_deg=float(
                            orbit.get("yaw_start_deg") or 0.0
                        ),
                    )
                )
            if frames:
                work_frames.extend(frames)
            if not work_frames:
                return {
                    "ok": False,
                    "error": "Provide frames and/or orbit",
                    "frames": [],
                }

            tmp_dir = tempfile.mkdtemp(prefix="mcp_view_seq_")
            prepared = []
            for index, frame in enumerate(work_frames):
                item = dict(frame)
                item["path"] = os.path.join(tmp_dir, f"frame_{index:03d}.png")
                prepared.append(item)
            results = save_view_sequence(prepared, width=width, height=height)
            encoded_frames = []
            for item in results:
                payload = {
                    "index": item["index"],
                    "ok": item["ok"],
                    "label": item.get("label"),
                    "view_name": item.get("view_name"),
                    "focus_objects": item.get("focus_objects") or [],
                    "yaw_deg": item.get("yaw_deg"),
                    "error": item.get("error"),
                    "image_base64": None,
                }
                path = item.get("path")
                if item.get("ok") and path and os.path.exists(path):
                    with open(path, "rb") as handle:
                        payload["image_base64"] = base64.b64encode(
                            handle.read()
                        ).decode("utf-8")
                encoded_frames.append(payload)
            for name in os.listdir(tmp_dir):
                try:
                    os.remove(os.path.join(tmp_dir, name))
                except OSError:
                    pass
            try:
                os.rmdir(tmp_dir)
            except OSError:
                pass
            ok_count = sum(
                1 for frame in encoded_frames if frame["ok"] and frame["image_base64"]
            )
            return {
                "ok": ok_count > 0,
                "frame_count": len(encoded_frames),
                "ok_count": ok_count,
                "frames": encoded_frames,
            }

        try:
            return self._dispatch_gui(_run)
        except Exception as exc:
            logger.exception("capture_view_sequence failed")
            return {"ok": False, "error": str(exc), "frames": []}

    def capture_view_sequence_to_disk(
        self,
        frames: list[dict[str, Any]] | None = None,
        width: int | None = None,
        height: int | None = None,
        orbit: dict[str, Any] | None = None,
        frame_dir: str | None = None,
    ) -> dict[str, Any]:
        """Capture frames to a directory and return PNG paths (for ffmpeg)."""

        def _run() -> dict[str, Any]:
            work_frames: list[dict[str, Any]] = []
            if orbit:
                work_frames.extend(
                    build_orbit_frames(
                        focus_objects=orbit.get("focus_objects"),
                        focus_object=orbit.get("focus_object"),
                        steps=int(orbit.get("steps") or 8),
                        view_name=str(orbit.get("view_name") or "Isometric"),
                        elevation_yaw_start_deg=float(
                            orbit.get("yaw_start_deg") or 0.0
                        ),
                    )
                )
            if frames:
                work_frames.extend(frames)
            if not work_frames:
                return {
                    "ok": False,
                    "error": "Provide frames and/or orbit",
                    "frame_paths": [],
                }
            out_dir = frame_dir or tempfile.mkdtemp(prefix="mcp_view_disk_")
            os.makedirs(out_dir, exist_ok=True)
            prepared = []
            for index, frame in enumerate(work_frames):
                item = dict(frame)
                item["path"] = os.path.join(out_dir, f"frame_{index:03d}.png")
                prepared.append(item)
            results = save_view_sequence(prepared, width=width, height=height)
            paths = [item["path"] for item in results if item.get("ok")]
            return {
                "ok": bool(paths),
                "frame_dir": out_dir,
                "frame_count": len(results),
                "ok_count": len(paths),
                "frame_paths": paths,
                "frames": results,
            }

        try:
            return self._dispatch_gui(_run)
        except Exception as exc:
            logger.exception("capture_view_sequence_to_disk failed")
            return {"ok": False, "error": str(exc), "frame_paths": []}

    def refresh_view(
        self,
        focus_objects: list[str] | None = None,
        focus_object: str | None = None,
        touch_objects: list[str] | None = None,
        fit: bool = False,
        capture: bool = False,
        view_name: str = "Isometric",
        width: int | None = None,
        height: int | None = None,
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            result = refresh_active_view(
                focus_object=focus_object,
                focus_objects=focus_objects,
                fit=fit,
            )
            if not result.get("ok"):
                return result
            if capture:
                fd, tmp_path = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                status = save_active_screenshot(
                    tmp_path,
                    view_name=view_name,
                    width=width,
                    height=height,
                    focus_object=focus_object,
                    focus_objects=focus_objects,
                )
                if status is True:
                    with open(tmp_path, "rb") as handle:
                        result["image_base64"] = base64.b64encode(handle.read()).decode(
                            "utf-8"
                        )
                else:
                    result["capture_error"] = str(status)
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            return result

        try:
            if touch_objects:
                return {
                    "ok": False,
                    "error_code": "PLACEMENT_REPAIR_REQUIRES_LEASE",
                    "error": (
                        "refresh_view is visual-only; use repair_view_placements "
                        "with an explicit leased document"
                    ),
                }
            return self._dispatch_gui(_run)
        except Exception as exc:
            logger.exception("refresh_view failed")
            return {"ok": False, "error": str(exc)}

    def repair_view_placements(
        self,
        doc_name: str,
        touch_objects: list[str],
        fit: bool = False,
    ) -> dict[str, Any]:
        return self._dispatch_gui(
            lambda: repair_placements_and_refresh(doc_name, touch_objects, fit=fit)
        )

    def animate_placement(
        self,
        doc_name: str,
        obj_name: str,
        keyframes: list[dict[str, Any]] | None = None,
        path_object: str | None = None,
        sample_count: int = 12,
        view_name: str = "Isometric",
        focus_objects: list[str] | None = None,
        width: int | None = None,
        height: int | None = None,
        encode_video: bool = False,
        fps: float = 8.0,
        output_path: str | None = None,
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            result = animate_object_placement(
                doc_name,
                obj_name,
                keyframes=keyframes,
                path_object=path_object,
                sample_count=sample_count,
                view_name=view_name,
                focus_objects=focus_objects,
                width=width,
                height=height,
            )
            if not result.get("ok"):
                return result
            encoded_frames = []
            for frame in result.get("frames", []):
                payload = dict(frame)
                path = frame.get("path")
                if frame.get("ok") and path and os.path.exists(path):
                    with open(path, "rb") as handle:
                        payload["image_base64"] = base64.b64encode(
                            handle.read()
                        ).decode("utf-8")
                encoded_frames.append(payload)
            result["frames"] = encoded_frames
            return result

        try:
            return self._dispatch_gui(_run)
        except Exception as exc:
            logger.exception("animate_placement failed")
            return {"ok": False, "error": str(exc)}

    def sketch_create(
        self,
        doc_name: str,
        sketch_name: str,
        body_name: str | None = None,
        attach_to: str | None = None,
    ) -> dict:
        res = self._dispatch_gui(
            lambda: self._sketch_create_gui(doc_name, sketch_name, body_name, attach_to)
        )
        if res is True:
            return {"success": True, "sketch_name": sketch_name}
        return {"success": False, "error": res}

    def sketch_add_geometry(
        self, doc_name: str, sketch_name: str, geometry: list
    ) -> dict:
        res = self._dispatch_gui(
            lambda: self._sketch_add_geometry_gui(doc_name, sketch_name, geometry)
        )
        if isinstance(res, list):
            return {"success": True, "indices": res}
        return {"success": False, "error": res}

    def sketch_add_constraint(
        self, doc_name: str, sketch_name: str, constraints: list
    ) -> dict:
        res = self._dispatch_gui(
            lambda: self._sketch_add_constraint_gui(doc_name, sketch_name, constraints)
        )
        if res is True:
            return {"success": True}
        return {"success": False, "error": res}

    def pad_feature(
        self,
        doc_name: str,
        sketch_name: str,
        pad_name: str,
        length: float,
        body_name: str | None = None,
        symmetric: bool = False,
        reversed_dir: bool = False,
    ) -> dict:
        res = self._dispatch_gui(
            lambda: self._pad_feature_gui(
                doc_name,
                sketch_name,
                pad_name,
                length,
                body_name,
                symmetric,
                reversed_dir,
            )
        )
        if res is True:
            return {"success": True, "pad_name": pad_name}
        return {"success": False, "error": res}

    def pocket_feature(
        self,
        doc_name: str,
        sketch_name: str,
        pocket_name: str,
        length: float,
        body_name: str | None = None,
        symmetric: bool = False,
        reversed_dir: bool = False,
    ) -> dict:
        res = self._dispatch_gui(
            lambda: self._pocket_feature_gui(
                doc_name,
                sketch_name,
                pocket_name,
                length,
                body_name,
                symmetric,
                reversed_dir,
            )
        )
        if res is True:
            return {"success": True, "pocket_name": pocket_name}
        return {"success": False, "error": res}

    def recompute_document(self, doc_name: str) -> dict:
        res = self._dispatch_gui(lambda: self._recompute_document_gui(doc_name))
        if res is True:
            return {"success": True}
        return {"success": False, "error": res}

    def undo(self, doc_name: str) -> dict:
        res = self._dispatch_gui(lambda: self._undo_gui(doc_name))
        if res is True:
            return {"success": True}
        return {"success": False, "error": res}

    def redo(self, doc_name: str) -> dict:
        res = self._dispatch_gui(lambda: self._redo_gui(doc_name))
        if res is True:
            return {"success": True}
        return {"success": False, "error": res}

    def get_recompute_log(self, doc_name: str) -> list:
        """Return recompute state for every object in a document (read-only)."""
        res = self._dispatch_gui(lambda: self._get_recompute_log_gui(doc_name))
        return res if isinstance(res, list) else [{"error": res}]

    def spreadsheet_create(self, doc_name: str, sheet_name: str) -> dict:
        res = self._dispatch_gui(
            lambda: self._spreadsheet_create_gui(doc_name, sheet_name)
        )
        return res if isinstance(res, dict) else {"success": False, "error": res}

    def spreadsheet_set_cells(
        self, doc_name: str, sheet_name: str, cells: list
    ) -> dict:
        res = self._dispatch_gui(
            lambda: self._spreadsheet_set_cells_gui(doc_name, sheet_name, cells)
        )
        return res if isinstance(res, dict) else {"success": False, "error": res}

    def spreadsheet_get_cells(
        self, doc_name: str, sheet_name: str, addresses: list
    ) -> dict:
        res = self._dispatch_gui(
            lambda: self._spreadsheet_get_cells_gui(doc_name, sheet_name, addresses)
        )
        return res if isinstance(res, dict) else {"success": False, "error": res}

    def spreadsheet_set_alias(
        self, doc_name: str, sheet_name: str, address: str, alias: str
    ) -> dict:
        res = self._dispatch_gui(
            lambda: self._spreadsheet_set_alias_gui(
                doc_name, sheet_name, address, alias
            )
        )
        return res if isinstance(res, dict) else {"success": False, "error": res}

    def spreadsheet_list_aliases(self, doc_name: str, sheet_name: str) -> dict:
        res = self._dispatch_gui(
            lambda: self._spreadsheet_list_aliases_gui(doc_name, sheet_name)
        )
        return res if isinstance(res, dict) else {"success": False, "error": res}

    def set_expression(
        self, doc_name: str, object_name: str, prop_path: str, expression: str
    ) -> dict:
        res = self._dispatch_gui(
            lambda: self._set_expression_gui(
                doc_name, object_name, prop_path, expression
            )
        )
        return res if isinstance(res, dict) else {"success": False, "error": res}

    def clear_expression(self, doc_name: str, object_name: str, prop_path: str) -> dict:
        res = self._dispatch_gui(
            lambda: self._clear_expression_gui(doc_name, object_name, prop_path)
        )
        return res if isinstance(res, dict) else {"success": False, "error": res}

    def list_expressions(self, doc_name: str, object_name: str) -> dict:
        res = self._dispatch_gui(
            lambda: self._list_expressions_gui(doc_name, object_name)
        )
        return res if isinstance(res, dict) else {"success": False, "error": res}

    def body_create(self, doc_name: str, body_name: str) -> dict:
        res = self._dispatch_gui(lambda: self._body_create_gui(doc_name, body_name))
        return res if isinstance(res, dict) else {"success": False, "error": res}

    def body_set_tip(self, doc_name: str, body_name: str, feature_name: str) -> dict:
        res = self._dispatch_gui(
            lambda: self._body_set_tip_gui(doc_name, body_name, feature_name)
        )
        return res if isinstance(res, dict) else {"success": False, "error": res}

    def sketch_attach(self, doc_name: str, sketch_name: str, support) -> dict:
        res = self._dispatch_gui(
            lambda: self._sketch_attach_gui(doc_name, sketch_name, support)
        )
        return res if isinstance(res, dict) else {"success": False, "error": res}

    def sketch_edit_constraint(
        self,
        doc_name: str,
        sketch_name: str,
        value=None,
        name=None,
        index=None,
    ) -> dict:
        res = self._dispatch_gui(
            lambda: self._sketch_edit_constraint_gui(
                doc_name, sketch_name, value, name, index
            )
        )
        return res if isinstance(res, dict) else {"success": False, "error": res}

    def diagnose_parametric(self, doc_name: str, object_name=None) -> dict:
        res = self._dispatch_gui(
            lambda: self._diagnose_parametric_gui(doc_name, object_name)
        )
        return res if isinstance(res, dict) else {"success": False, "error": res}

    def _get_recompute_log_gui(self, doc_name: str) -> list:
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            return [{"error": f"Document '{doc_name}' not found"}]
        results = []
        for obj in doc.Objects:
            try:
                st = list(getattr(obj, "State", []))
                exprs = []
                for item in getattr(obj, "ExpressionEngine", None) or []:
                    try:
                        if isinstance(item, (list, tuple)) and len(item) >= 2:
                            exprs.append(
                                {"prop": str(item[0]), "expression": str(item[1])}
                            )
                        else:
                            exprs.append({"raw": str(item)})
                    except Exception as ee:
                        exprs.append({"error": str(ee)})
                entry = {
                    "name": obj.Name,
                    "label": getattr(obj, "Label", obj.Name),
                    "type_id": getattr(obj, "TypeId", ""),
                    "state": st,
                    "valid": not any(s in ("Invalid", "Error") for s in st),
                    "expression_count": len(exprs),
                }
                if exprs:
                    entry["expressions"] = exprs
                if any(s in ("Invalid", "Error") for s in st) and exprs:
                    entry["expression_hint"] = (
                        "object invalid with bound expressions; check diagnose_parametric"
                    )
                results.append(entry)
            except Exception as e:
                results.append({"name": getattr(obj, "Name", "?"), "error": str(e)})
        return results

    def get_sketch_diagnostics(self, doc_name: str, sketch_name: str) -> dict:
        """Return solver diagnostics for a Sketcher sketch (read-only)."""
        res = self._dispatch_gui(
            lambda: self._get_sketch_diagnostics_gui(doc_name, sketch_name)
        )
        return res if isinstance(res, dict) else {"error": res}

    def _get_sketch_diagnostics_gui(self, doc_name: str, sketch_name: str) -> dict:
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            return {"error": f"Document '{doc_name}' not found"}
        sk = doc.getObject(sketch_name)
        if not sk:
            return {"error": f"Sketch '{sketch_name}' not found"}
        info = {
            "name": sk.Name,
            "geometry_count": len(sk.Geometry) if hasattr(sk, "Geometry") else 0,
            "constraint_count": len(sk.Constraints)
            if hasattr(sk, "Constraints")
            else 0,
            "state": list(getattr(sk, "State", [])),
            "conflicting_constraints": list(getattr(sk, "ConflictingConstraints", [])),
            "redundant_constraints": list(getattr(sk, "RedundantConstraints", [])),
            "malformed_constraints": list(getattr(sk, "MalformedConstraints", [])),
            "solver_message": getattr(sk, "SolverMessage", None),
            "is_closed": None,
        }
        try:
            shape = sk.Shape
            if shape and not shape.isNull():
                info["is_closed"] = shape.isClosed()
        except Exception:
            pass
        return info

    def close_document(self, doc_name: str) -> dict:
        res = self._dispatch_gui(lambda: self._close_document_gui(doc_name))
        if res is True:
            return {"success": True}
        return {"success": False, "error": res}

    def snapshot(self, doc_name: str) -> dict:
        """I7 — save the current document into a ring buffer of the last 5
        snapshots kept on the FreeCAD module (shared with the execute_code
        snapshot tool). Returns {ok, snapshot_id, doc, count}."""
        res = self._dispatch_gui(lambda: self._snapshot_gui(doc_name))
        if isinstance(res, dict):
            return res
        return {"ok": False, "error": res}

    def restore(self, doc_name: str, snapshot_id: str | None = None) -> dict:
        """I7 — restore a snapshot in place (closes the current doc and reopens
        the snapshot file). Latest snapshot when snapshot_id is None. Shares the
        FreeCAD._mcp_snapshots ring buffer with the execute_code restore tool."""
        res = self._dispatch_gui(lambda: self._restore_gui(doc_name, snapshot_id))
        if isinstance(res, dict):
            return res
        return {"ok": False, "error": res}

    def solve_assembly(self, doc_name: str, assembly_name: str) -> dict:
        """I9 — re-solve an Assembly via the real internal solver. Tries
        assembly.solve() (C++), then JointObject.solveIfAllowed, then recompute."""
        res = self._dispatch_gui(
            lambda: self._solve_assembly_gui(doc_name, assembly_name)
        )
        if isinstance(res, dict):
            return res
        return {"ok": False, "error": res}

    def _get_objects_gui(self, doc_name):
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            return []
        results = []
        for obj in doc.Objects:
            try:
                results.append(serialize_object(obj))
            except Exception as e:
                results.append(
                    {
                        "Name": getattr(obj, "Name", "<unknown>"),
                        "Label": getattr(obj, "Label", "<unknown>"),
                        "TypeId": getattr(obj, "TypeId", "<unknown>"),
                        "error": f"Serialization failed: {e}",
                    }
                )
        return results if results else []

    def _get_object_gui(self, doc_name, obj_name):
        doc = FreeCAD.getDocument(doc_name)
        if doc:
            obj = doc.getObject(obj_name)
            if obj:
                try:
                    return serialize_object(obj)
                except Exception as e:
                    return {"Name": obj_name, "error": str(e)}
        return False

    def _create_document_gui(self, name):
        doc = FreeCAD.newDocument(name)
        doc.recompute()
        FreeCAD.Console.PrintMessage(f"Document '{name}' created via RPC.\n")
        return True

    def _create_object_gui(self, doc_name, obj: Object):
        doc = FreeCAD.getDocument(doc_name)
        if doc:
            try:
                if obj.type == "Fem::FemMeshGmsh" and obj.analysis:
                    from femmesh.gmshtools import GmshTools

                    res = getattr(doc, obj.analysis).addObject(
                        ObjectsFem.makeMeshGmsh(doc, obj.name)
                    )[0]
                    if "Part" in obj.properties:
                        target_obj = doc.getObject(obj.properties["Part"])
                        if target_obj:
                            res.Part = target_obj
                        else:
                            raise ValueError(
                                f"Referenced object '{obj.properties['Part']}' not found."
                            )
                        del obj.properties["Part"]
                    else:
                        raise ValueError("'Part' property not found in properties.")

                    for param, value in obj.properties.items():
                        if hasattr(res, param):
                            setattr(res, param, value)
                    doc.recompute()

                    gmsh_tools = GmshTools(res)
                    gmsh_tools.create_mesh()
                    FreeCAD.Console.PrintMessage(
                        f"FEM Mesh '{res.Name}' generated successfully in '{doc_name}'.\n"
                    )
                elif obj.type.startswith("Fem::"):
                    fem_make_methods = {
                        "MaterialCommon": ObjectsFem.makeMaterialSolid,
                        "AnalysisPython": ObjectsFem.makeAnalysis,
                    }
                    obj_type_short = obj.type.split("::")[1]
                    method_name = "make" + obj_type_short
                    make_method = fem_make_methods.get(
                        obj_type_short, getattr(ObjectsFem, method_name, None)
                    )

                    if callable(make_method):
                        res = make_method(doc, obj.name)
                        set_object_property(doc, res, obj.properties)
                        FreeCAD.Console.PrintMessage(
                            f"FEM object '{res.Name}' created with '{method_name}'.\n"
                        )
                    else:
                        raise ValueError(
                            f"No creation method '{method_name}' found in ObjectsFem."
                        )
                    if obj.type != "Fem::AnalysisPython" and obj.analysis:
                        getattr(doc, obj.analysis).addObject(res)
                else:
                    res = doc.addObject(obj.type, obj.name)
                    set_object_property(doc, res, obj.properties)
                    FreeCAD.Console.PrintMessage(
                        f"{res.TypeId} '{res.Name}' added to '{doc_name}' via RPC.\n"
                    )

                doc.recompute()
                return True
            except Exception as e:
                return str(e)
        else:
            FreeCAD.Console.PrintError(f"Document '{doc_name}' not found.\n")
            return f"Document '{doc_name}' not found.\n"

    def _edit_object_gui(self, doc_name: str, obj: Object):
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            FreeCAD.Console.PrintError(f"Document '{doc_name}' not found.\n")
            return f"Document '{doc_name}' not found.\n"

        obj_ins = doc.getObject(obj.name)
        if not obj_ins:
            FreeCAD.Console.PrintError(
                f"Object '{obj.name}' not found in document '{doc_name}'.\n"
            )
            return f"Object '{obj.name}' not found in document '{doc_name}'.\n"

        try:
            # For Fem::ConstraintFixed
            if hasattr(obj_ins, "References") and "References" in obj.properties:
                refs = []
                for ref_name, face in obj.properties["References"]:
                    ref_obj = doc.getObject(ref_name)
                    if ref_obj:
                        refs.append((ref_obj, face))
                    else:
                        raise ValueError(f"Referenced object '{ref_name}' not found.")
                obj_ins.References = refs
                FreeCAD.Console.PrintMessage(
                    f"References updated for '{obj.name}' in '{doc_name}'.\n"
                )
                # delete References from properties
                del obj.properties["References"]
            set_object_property(doc, obj_ins, obj.properties)
            doc.recompute()
            FreeCAD.Console.PrintMessage(f"Object '{obj.name}' updated via RPC.\n")
            return True
        except Exception as e:
            return str(e)

    def _delete_object_gui(self, doc_name: str, obj_name: str):
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            FreeCAD.Console.PrintError(f"Document '{doc_name}' not found.\n")
            return f"Document '{doc_name}' not found.\n"

        try:
            doc.removeObject(obj_name)
            doc.recompute()
            FreeCAD.Console.PrintMessage(f"Object '{obj_name}' deleted via RPC.\n")
            return True
        except Exception as e:
            return str(e)

    def _insert_part_from_library(self, doc_name, relative_path):
        try:
            insert_part_from_library(doc_name, relative_path)
            return True
        except Exception as e:
            return str(e)

    def _reload_document_gui(self, doc_name: str):
        if doc_name not in FreeCAD.listDocuments():
            return f"Document '{doc_name}' is not loaded."
        doc = FreeCAD.getDocument(doc_name)
        file_path = doc.FileName
        if not file_path:
            return (
                f"Document '{doc_name}' has no file on disk "
                "(unsaved scratch document); nothing to reload from."
            )
        if not os.path.exists(file_path):
            return f"File for '{doc_name}' not found at {file_path!r}."
        session_uuid = None
        if document_lease_service is not None:
            try:
                identity = document_identity_service.resolve(
                    {"document_name": doc_name}
                )
                status = document_lease_service.get(
                    {"document_session_uuid": identity.session_uuid}
                )
                if status is not None:
                    baseline_data = status.get("document_state", {}).get("baseline")
                    baseline = _import_document_lease().FileBaseline.from_dict(
                        baseline_data
                    )
                    if baseline is None:
                        return "Reload requires a verified saved baseline."
                    compare_file_to_baseline(
                        file_path,
                        baseline,
                        platform=document_identity_service.platform,
                    )
                    session_uuid = identity.session_uuid
            except Exception as exc:
                return f"Reload preflight rejected the document: {exc}"
        # Close, then reopen from the same file. Reopen preserves the
        # original document name when the file was previously saved
        # under that name.
        FreeCAD.closeDocument(doc_name)
        reopened = FreeCAD.openDocument(file_path)
        if reopened is None:
            return f"FreeCAD did not reopen '{file_path}'."
        if session_uuid is not None:
            rebound = document_identity_service.rebind_document(session_uuid, reopened)
            if rebound.comparison_key != identity.comparison_key:
                return "Reload rebound the document to an unexpected file."
        FreeCAD.Console.PrintMessage(
            f"Document '{doc_name}' reloaded from '{file_path}' via RPC.\n"
        )
        return True

    def _run_fem_analysis_gui(self, doc_name: str, analysis_name: str):
        return _run_fem_analysis(doc_name, analysis_name)

    def _save_active_screenshot(
        self,
        save_path: str,
        view_name: str | None = "Isometric",
        width: int | None = None,
        height: int | None = None,
        focus_object: str | None = None,
        focus_objects: list[str] | None = None,
        yaw_deg: float | None = None,
    ):
        return save_active_screenshot(
            save_path,
            view_name or "Isometric",
            width,
            height,
            focus_object=focus_object,
            focus_objects=focus_objects,
            yaw_deg=yaw_deg,
        )

    def _sketch_create_gui(self, doc_name, sketch_name, body_name, attach_to):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."

            if body_name:
                body = doc.getObject(body_name)
                if not body:
                    return f"Body '{body_name}' not found."
                sketch = body.newObject("Sketcher::SketchObject", sketch_name)
            else:
                sketch = doc.addObject("Sketcher::SketchObject", sketch_name)

            if attach_to:
                if attach_to in ("XY_Plane", "XZ_Plane", "YZ_Plane"):
                    plane_obj = None
                    for obj in doc.Objects:
                        if obj.TypeId == "App::Origin":
                            for feat in getattr(obj, "OriginFeatures", []):
                                if feat.Label == attach_to:
                                    plane_obj = feat
                                    break
                        if plane_obj:
                            break
                    if plane_obj:
                        sketch.AttachmentSupport = [(plane_obj, "")]
                        sketch.MapMode = "FlatFace"
                    else:
                        # Fall back to placement rotation
                        if attach_to == "XZ_Plane":
                            sketch.Placement = FreeCAD.Placement(
                                FreeCAD.Vector(0, 0, 0),
                                FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90),
                            )
                        elif attach_to == "YZ_Plane":
                            sketch.Placement = FreeCAD.Placement(
                                FreeCAD.Vector(0, 0, 0),
                                FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), -90),
                            )
                elif ":" in attach_to:
                    obj_name, face = attach_to.split(":", 1)
                    ref_obj = doc.getObject(obj_name)
                    if not ref_obj:
                        return f"Object '{obj_name}' not found for attach_to."
                    sketch.AttachmentSupport = [(ref_obj, face)]
                    sketch.MapMode = "FlatFace"

            doc.recompute()
            FreeCAD.Console.PrintMessage(
                f"Sketch '{sketch_name}' created in '{doc_name}'.\n"
            )
            return True
        except Exception as e:
            return str(e)

    def _sketch_add_geometry_gui(self, doc_name, sketch_name, geometry):
        try:
            import math
            import Part

            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            sketch = doc.getObject(sketch_name)
            if not sketch:
                return f"Sketch '{sketch_name}' not found."

            indices = []
            for geom in geometry:
                geom_type = geom.get("type", "").lower()
                construction = geom.get("construction", False)

                if geom_type == "line":
                    s, e = geom["start"], geom["end"]
                    seg = Part.LineSegment(
                        FreeCAD.Vector(s.get("x", 0), s.get("y", 0), 0),
                        FreeCAD.Vector(e.get("x", 0), e.get("y", 0), 0),
                    )
                    indices.append(sketch.addGeometry(seg, construction))

                elif geom_type == "circle":
                    c = geom.get("center", {"x": 0, "y": 0})
                    r = geom.get("radius", 1)
                    circle = Part.Circle(
                        FreeCAD.Vector(c.get("x", 0), c.get("y", 0), 0),
                        FreeCAD.Vector(0, 0, 1),
                        r,
                    )
                    indices.append(sketch.addGeometry(circle, construction))

                elif geom_type == "arc":
                    c = geom.get("center", {"x": 0, "y": 0})
                    r = geom.get("radius", 1)
                    start_a = math.radians(geom.get("start_angle", 0))
                    end_a = math.radians(geom.get("end_angle", 90))
                    base_circle = Part.Circle(
                        FreeCAD.Vector(c.get("x", 0), c.get("y", 0), 0),
                        FreeCAD.Vector(0, 0, 1),
                        r,
                    )
                    arc = Part.ArcOfCircle(base_circle, start_a, end_a)
                    indices.append(sketch.addGeometry(arc, construction))

                elif geom_type == "rectangle":
                    x1, y1 = geom.get("x1", 0), geom.get("y1", 0)
                    x2, y2 = geom.get("x2", 10), geom.get("y2", 10)
                    corners = [
                        (FreeCAD.Vector(x1, y1, 0), FreeCAD.Vector(x2, y1, 0)),
                        (FreeCAD.Vector(x2, y1, 0), FreeCAD.Vector(x2, y2, 0)),
                        (FreeCAD.Vector(x2, y2, 0), FreeCAD.Vector(x1, y2, 0)),
                        (FreeCAD.Vector(x1, y2, 0), FreeCAD.Vector(x1, y1, 0)),
                    ]
                    for p1, p2 in corners:
                        idx = sketch.addGeometry(Part.LineSegment(p1, p2), construction)
                        indices.append(idx)

                elif geom_type == "point":
                    pt = Part.Point(
                        FreeCAD.Vector(geom.get("x", 0), geom.get("y", 0), 0)
                    )
                    indices.append(sketch.addGeometry(pt, construction))

                else:
                    return f"Unknown geometry type: '{geom_type}'"

            doc.recompute()
            return indices
        except Exception as e:
            return str(e)

    def _sketch_add_constraint_gui(self, doc_name, sketch_name, constraints):
        try:
            import Sketcher

            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            sketch = doc.getObject(sketch_name)
            if not sketch:
                return f"Sketch '{sketch_name}' not found."

            for c in constraints:
                t = c.get("type", "")
                name = c.get("name")
                idx = None
                if t == "Coincident":
                    idx = sketch.addConstraint(
                        Sketcher.Constraint(
                            "Coincident", c["geo1"], c["pos1"], c["geo2"], c["pos2"]
                        )
                    )
                elif t == "Horizontal":
                    idx = sketch.addConstraint(
                        Sketcher.Constraint("Horizontal", c["geo"])
                    )
                elif t == "Vertical":
                    idx = sketch.addConstraint(
                        Sketcher.Constraint("Vertical", c["geo"])
                    )
                elif t == "Distance":
                    if "geo2" in c:
                        idx = sketch.addConstraint(
                            Sketcher.Constraint(
                                "Distance",
                                c["geo1"],
                                c.get("pos1", 0),
                                c["geo2"],
                                c.get("pos2", 0),
                                c["value"],
                            )
                        )
                    elif "pos" in c:
                        idx = sketch.addConstraint(
                            Sketcher.Constraint(
                                "Distance", c["geo"], c["pos"], c["value"]
                            )
                        )
                    else:
                        idx = sketch.addConstraint(
                            Sketcher.Constraint("Distance", c["geo"], c["value"])
                        )
                elif t == "DistanceX":
                    if "pos" in c:
                        idx = sketch.addConstraint(
                            Sketcher.Constraint(
                                "DistanceX", c["geo"], c["pos"], c["value"]
                            )
                        )
                    else:
                        idx = sketch.addConstraint(
                            Sketcher.Constraint("DistanceX", c["geo"], c["value"])
                        )
                elif t == "DistanceY":
                    if "pos" in c:
                        idx = sketch.addConstraint(
                            Sketcher.Constraint(
                                "DistanceY", c["geo"], c["pos"], c["value"]
                            )
                        )
                    else:
                        idx = sketch.addConstraint(
                            Sketcher.Constraint("DistanceY", c["geo"], c["value"])
                        )
                elif t == "Radius":
                    idx = sketch.addConstraint(
                        Sketcher.Constraint("Radius", c["geo"], c["value"])
                    )
                elif t == "Diameter":
                    idx = sketch.addConstraint(
                        Sketcher.Constraint("Diameter", c["geo"], c["value"])
                    )
                elif t == "Angle":
                    if "geo2" in c:
                        idx = sketch.addConstraint(
                            Sketcher.Constraint(
                                "Angle",
                                c["geo1"],
                                c.get("pos1", 0),
                                c["geo2"],
                                c.get("pos2", 0),
                                c["value"],
                            )
                        )
                    else:
                        idx = sketch.addConstraint(
                            Sketcher.Constraint("Angle", c["geo"], c["value"])
                        )
                elif t == "Parallel":
                    idx = sketch.addConstraint(
                        Sketcher.Constraint("Parallel", c["geo1"], c["geo2"])
                    )
                elif t == "Perpendicular":
                    idx = sketch.addConstraint(
                        Sketcher.Constraint("Perpendicular", c["geo1"], c["geo2"])
                    )
                elif t == "Equal":
                    idx = sketch.addConstraint(
                        Sketcher.Constraint("Equal", c["geo1"], c["geo2"])
                    )
                elif t == "Symmetric":
                    idx = sketch.addConstraint(
                        Sketcher.Constraint(
                            "Symmetric",
                            c["geo1"],
                            c["pos1"],
                            c["geo2"],
                            c["pos2"],
                            c["geo3"],
                            c.get("pos3", 0),
                        )
                    )
                elif t == "PointOnObject":
                    idx = sketch.addConstraint(
                        Sketcher.Constraint(
                            "PointOnObject", c["geo1"], c["pos1"], c["geo2"]
                        )
                    )
                elif t == "Tangent":
                    idx = sketch.addConstraint(
                        Sketcher.Constraint("Tangent", c["geo1"], c["geo2"])
                    )
                elif t == "Block":
                    idx = sketch.addConstraint(Sketcher.Constraint("Block", c["geo"]))
                else:
                    return f"Unknown constraint type: '{t}'"
                if name and idx is not None:
                    try:
                        sketch.renameConstraint(idx, str(name))
                    except Exception:
                        pass

            doc.recompute()
            return True
        except Exception as e:
            return str(e)

    def _spreadsheet_create_gui(self, doc_name, sheet_name):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            if doc.getObject(sheet_name):
                return f"Object already exists: {sheet_name}"
            sheet = doc.addObject("Spreadsheet::Sheet", sheet_name)
            doc.recompute()
            return {"success": True, "sheet": sheet.Name}
        except Exception as e:
            return str(e)

    def _spreadsheet_set_cells_gui(self, doc_name, sheet_name, cells):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            sheet = doc.getObject(sheet_name)
            if not sheet:
                return f"Spreadsheet '{sheet_name}' not found."
            updated = []
            for cell in cells or []:
                addr = cell.get("address") or cell.get("addr")
                alias = cell.get("alias")
                if not addr and alias:
                    try:
                        addr = sheet.getCellFromAlias(alias)
                    except Exception:
                        addr = None
                if not addr:
                    return f"Cell requires address or resolvable alias: {cell!r}"
                if "value" in cell:
                    sheet.set(str(addr), str(cell["value"]))
                if alias and cell.get("address"):
                    sheet.setAlias(str(addr), str(alias))
                elif cell.get("set_alias"):
                    sheet.setAlias(str(addr), str(cell["set_alias"]))
                updated.append({"address": str(addr), "alias": alias})
            doc.recompute()
            return {"success": True, "sheet": sheet.Name, "updated": updated}
        except Exception as e:
            return str(e)

    def _spreadsheet_get_cells_gui(self, doc_name, sheet_name, addresses):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            sheet = doc.getObject(sheet_name)
            if not sheet:
                return f"Spreadsheet '{sheet_name}' not found."
            out = []
            for item in addresses or []:
                addr = item
                alias = None
                if isinstance(item, dict):
                    addr = item.get("address") or item.get("addr")
                    alias = item.get("alias")
                    if not addr and alias:
                        addr = sheet.getCellFromAlias(alias)
                row = {"address": str(addr)}
                try:
                    row["alias"] = sheet.getAlias(str(addr))
                except Exception:
                    row["alias"] = None
                try:
                    row["contents"] = sheet.getContents(str(addr))
                except Exception as e:
                    row["contents_error"] = str(e)
                try:
                    row["value"] = sheet.get(str(addr))
                except Exception as e:
                    row["value_error"] = str(e)
                out.append(row)
            return {"success": True, "sheet": sheet.Name, "cells": out}
        except Exception as e:
            return str(e)

    def _spreadsheet_set_alias_gui(self, doc_name, sheet_name, address, alias):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            sheet = doc.getObject(sheet_name)
            if not sheet:
                return f"Spreadsheet '{sheet_name}' not found."
            sheet.setAlias(str(address), str(alias))
            doc.recompute()
            return {
                "success": True,
                "sheet": sheet.Name,
                "address": address,
                "alias": alias,
            }
        except Exception as e:
            return str(e)

    def _spreadsheet_list_aliases_gui(self, doc_name, sheet_name):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            sheet = doc.getObject(sheet_name)
            if not sheet:
                return f"Spreadsheet '{sheet_name}' not found."
            aliases = {}
            addrs = []
            if hasattr(sheet, "getNonEmptyCells"):
                try:
                    addrs = list(sheet.getNonEmptyCells())
                except Exception:
                    addrs = []
            if not addrs:
                for col in range(1, 27):
                    for row in range(1, 101):
                        addrs.append(chr(64 + col) + str(row))
            for addr in addrs:
                try:
                    alias = sheet.getAlias(str(addr))
                except Exception:
                    alias = None
                if alias:
                    aliases[str(alias)] = str(addr)
            return {"success": True, "sheet": sheet.Name, "aliases": aliases}
        except Exception as e:
            return str(e)

    def _set_expression_gui(self, doc_name, object_name, prop_path, expression):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            obj = doc.getObject(object_name)
            if not obj:
                return f"Object '{object_name}' not found."
            try:
                obj.setExpression(prop_path, expression)
            except Exception as e:
                return {
                    "success": False,
                    "error": "expression_error",
                    "object": object_name,
                    "prop_path": prop_path,
                    "expression": expression,
                    "message": str(e),
                }
            doc.recompute()
            state = list(getattr(obj, "State", []))
            invalid = any(s in ("Invalid", "Error") for s in state)
            return {
                "success": not invalid,
                "object": obj.Name,
                "prop_path": prop_path,
                "expression": expression,
                "state": state,
                "valid": not invalid,
            }
        except Exception as e:
            return str(e)

    def _clear_expression_gui(self, doc_name, object_name, prop_path):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            obj = doc.getObject(object_name)
            if not obj:
                return f"Object '{object_name}' not found."
            if hasattr(obj, "clearExpression"):
                obj.clearExpression(prop_path)
            else:
                obj.setExpression(prop_path, None)
            doc.recompute()
            return {"success": True, "object": obj.Name, "prop_path": prop_path}
        except Exception as e:
            return str(e)

    def _list_expressions_gui(self, doc_name, object_name):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            obj = doc.getObject(object_name)
            if not obj:
                return f"Object '{object_name}' not found."
            exprs = []
            for item in getattr(obj, "ExpressionEngine", None) or []:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    exprs.append({"prop": str(item[0]), "expression": str(item[1])})
                else:
                    exprs.append({"raw": str(item)})
            return {
                "success": True,
                "object": obj.Name,
                "expressions": exprs,
                "count": len(exprs),
            }
        except Exception as e:
            return str(e)

    def _body_create_gui(self, doc_name, body_name):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            if doc.getObject(body_name):
                return f"Object already exists: {body_name}"
            body = doc.addObject("PartDesign::Body", body_name)
            doc.recompute()
            return {"success": True, "body": body.Name}
        except Exception as e:
            return str(e)

    def _body_set_tip_gui(self, doc_name, body_name, feature_name):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            body = doc.getObject(body_name)
            if not body:
                return f"Body '{body_name}' not found."
            feat = doc.getObject(feature_name)
            if not feat:
                return f"Feature '{feature_name}' not found."
            body.Tip = feat
            doc.recompute()
            tip = getattr(body, "Tip", None)
            return {
                "success": True,
                "body": body.Name,
                "tip": getattr(tip, "Name", None),
            }
        except Exception as e:
            return str(e)

    def _sketch_attach_gui(self, doc_name, sketch_name, support):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            sketch = doc.getObject(sketch_name)
            if not sketch:
                return f"Sketch '{sketch_name}' not found."
            attached = None
            if isinstance(support, str):
                if support in ("XY_Plane", "XZ_Plane", "YZ_Plane"):
                    plane = None
                    body = None
                    for obj in doc.Objects:
                        if getattr(
                            obj, "TypeId", ""
                        ) == "PartDesign::Body" and sketch in getattr(obj, "Group", []):
                            body = obj
                            break
                    origins = []
                    if body is not None and getattr(body, "Origin", None) is not None:
                        origins.append(body.Origin)
                    for o in doc.Objects:
                        if (
                            getattr(o, "TypeId", "") == "App::Origin"
                            and o not in origins
                        ):
                            origins.append(o)
                    for origin in origins:
                        for feat in getattr(origin, "OriginFeatures", []) or []:
                            if (
                                getattr(feat, "Label", "") == support
                                or getattr(feat, "Name", "") == support
                            ):
                                plane = feat
                                break
                        if plane is None and hasattr(origin, support):
                            plane = getattr(origin, support)
                        if plane is not None:
                            break
                    if plane is None:
                        return f"Origin plane not found: {support}"
                    sketch.AttachmentSupport = [(plane, "")]
                    sketch.MapMode = "FlatFace"
                    attached = {
                        "object": plane.Name,
                        "subname": "",
                        "kind": "origin_plane",
                        "plane": support,
                    }
                elif ":" in support:
                    obj_name, sub = support.split(":", 1)
                    ref = doc.getObject(obj_name)
                    if not ref:
                        return f"Support object not found: {obj_name}"
                    sketch.AttachmentSupport = [(ref, sub)]
                    sketch.MapMode = "FlatFace"
                    attached = {"object": ref.Name, "subname": sub, "kind": "face_ref"}
                else:
                    return f"Unsupported support string: {support}"
            elif isinstance(support, dict):
                obj_name = support.get("object") or support.get("object_name")
                sub = support.get("subname") or support.get("sub") or ""
                ref = doc.getObject(obj_name)
                if not ref:
                    return f"Support object not found: {obj_name}"
                sketch.AttachmentSupport = [(ref, sub)]
                sketch.MapMode = "FlatFace"
                attached = {"object": ref.Name, "subname": sub, "kind": "dict_ref"}
            else:
                return "support must be str or dict"
            doc.recompute()
            return {"success": True, "sketch": sketch.Name, "attached": attached}
        except Exception as e:
            return str(e)

    def _sketch_edit_constraint_gui(self, doc_name, sketch_name, value, name, index):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            sketch = doc.getObject(sketch_name)
            if not sketch:
                return f"Sketch '{sketch_name}' not found."
            idx = None
            if name is not None:
                for i, c in enumerate(getattr(sketch, "Constraints", []) or []):
                    if getattr(c, "Name", "") == name:
                        idx = i
                        break
                if idx is None:
                    return f"Constraint name not found: {name}"
            elif index is not None:
                idx = int(index)
            else:
                return "Provide constraint name or index"
            if value is not None:
                sketch.setDatum(idx, float(value))
            doc.recompute()
            after = None
            try:
                after = float(sketch.getDatum(idx))
            except Exception:
                after = None
            return {
                "success": True,
                "sketch": sketch.Name,
                "index": idx,
                "name": getattr(sketch.Constraints[idx], "Name", ""),
                "after": after,
            }
        except Exception as e:
            return str(e)

    def _diagnose_parametric_gui(self, doc_name, object_name=None):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            targets = [doc.getObject(object_name)] if object_name else list(doc.Objects)
            targets = [t for t in targets if t is not None]
            if object_name and not targets:
                return f"Object '{object_name}' not found."
            invalid = []
            expression_issues = []
            sketches = []
            for obj in targets:
                state = list(getattr(obj, "State", []))
                if any(s in ("Invalid", "Error") for s in state):
                    invalid.append(
                        {
                            "name": obj.Name,
                            "label": getattr(obj, "Label", obj.Name),
                            "type": getattr(obj, "TypeId", ""),
                            "state": state,
                        }
                    )
                for item in getattr(obj, "ExpressionEngine", None) or []:
                    try:
                        prop = (
                            str(item[0])
                            if isinstance(item, (list, tuple)) and len(item) >= 1
                            else "?"
                        )
                        expr = (
                            str(item[1])
                            if isinstance(item, (list, tuple)) and len(item) >= 2
                            else str(item)
                        )
                        bound = (
                            obj.getExpression(prop)
                            if hasattr(obj, "getExpression")
                            else None
                        )
                        if bound is None and expr:
                            expression_issues.append(
                                {
                                    "object": obj.Name,
                                    "prop": prop,
                                    "expression": expr,
                                    "issue": "missing_binding",
                                }
                            )
                    except Exception as e:
                        expression_issues.append(
                            {
                                "object": obj.Name,
                                "issue": "expression_error",
                                "message": str(e),
                            }
                        )
                if getattr(obj, "TypeId", "") == "Sketcher::SketchObject":
                    sketches.append(
                        {
                            "name": obj.Name,
                            "geometry_count": len(getattr(obj, "Geometry", []) or []),
                            "constraint_count": len(
                                getattr(obj, "Constraints", []) or []
                            ),
                            "state": state,
                            "conflicting": list(
                                getattr(obj, "ConflictingConstraints", []) or []
                            ),
                            "redundant": list(
                                getattr(obj, "RedundantConstraints", []) or []
                            ),
                            "malformed": list(
                                getattr(obj, "MalformedConstraints", []) or []
                            ),
                        }
                    )
            return {
                "success": len(invalid) == 0 and len(expression_issues) == 0,
                "document": doc.Name,
                "object": object_name,
                "invalid_objects": invalid,
                "expression_issues": expression_issues,
                "sketches": sketches,
            }
        except Exception as e:
            return str(e)

    def _pad_feature_gui(
        self,
        doc_name,
        sketch_name,
        pad_name,
        length,
        body_name,
        symmetric,
        reversed_dir,
    ):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            sketch = doc.getObject(sketch_name)
            if not sketch:
                return f"Sketch '{sketch_name}' not found."

            if body_name and not doc.getObject(body_name):
                return f"Body '{body_name}' not found."
            body = doc.getObject(body_name) if body_name else None
            if not body:
                for obj in doc.Objects:
                    if obj.TypeId == "PartDesign::Body" and sketch in obj.Group:
                        body = obj
                        break

            # Strict PartDesign: never fall back to a loose document-level feature.
            if body is None or body.TypeId != "PartDesign::Body":
                return (
                    f"No PartDesign::Body found to own pad '{pad_name}'. Sketch "
                    f"'{sketch_name}' is not inside a Body; create a Body first."
                )
            pad = body.newObject("PartDesign::Pad", pad_name)

            pad.Profile = (sketch, [""])
            pad.Length = length
            _set_extrusion_symmetric(pad, symmetric)
            _set_feature_bool(pad, ("Reversed",), reversed_dir)
            body.Tip = pad
            sketch.Visibility = False
            doc.recompute()
            FreeCAD.Console.PrintMessage(f"Pad '{pad_name}' created in '{doc_name}'.\n")
            return True
        except Exception as e:
            return str(e)

    def _pocket_feature_gui(
        self,
        doc_name,
        sketch_name,
        pocket_name,
        length,
        body_name,
        symmetric,
        reversed_dir,
    ):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            sketch = doc.getObject(sketch_name)
            if not sketch:
                return f"Sketch '{sketch_name}' not found."

            if body_name and not doc.getObject(body_name):
                return f"Body '{body_name}' not found."
            body = doc.getObject(body_name) if body_name else None
            if not body:
                for obj in doc.Objects:
                    if obj.TypeId == "PartDesign::Body" and sketch in obj.Group:
                        body = obj
                        break

            # Strict PartDesign: never fall back to a loose document-level feature.
            if body is None or body.TypeId != "PartDesign::Body":
                return (
                    f"No PartDesign::Body found to own pocket '{pocket_name}'. Sketch "
                    f"'{sketch_name}' is not inside a Body; create a Body first."
                )
            pocket = body.newObject("PartDesign::Pocket", pocket_name)

            pocket.Profile = (sketch, [""])
            pocket.Length = length
            _set_extrusion_symmetric(pocket, symmetric)
            _set_feature_bool(pocket, ("Reversed",), reversed_dir)
            body.Tip = pocket
            sketch.Visibility = False
            doc.recompute()
            FreeCAD.Console.PrintMessage(
                f"Pocket '{pocket_name}' created in '{doc_name}'.\n"
            )
            return True
        except Exception as e:
            return str(e)

    def _recompute_document_gui(self, doc_name):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            doc.recompute()
            return True
        except Exception as e:
            return str(e)

    def _undo_gui(self, doc_name):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            doc.undo()
            return True
        except Exception as e:
            return str(e)

    def _redo_gui(self, doc_name):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            doc.redo()
            return True
        except Exception as e:
            return str(e)

    def _close_document_gui(self, doc_name: str):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return f"Document '{doc_name}' not found."
            if document_lease_service is not None:
                try:
                    identity = document_identity_service.resolve(
                        {"document_name": doc_name}
                    )
                    active = document_lease_service.get(
                        {"document_session_uuid": identity.session_uuid}
                    )
                except Exception:
                    active = None
                if active is not None:
                    return (
                        "A leased document cannot be closed by the generic RPC. "
                        "Finalize and verify the save first; terminal close is "
                        "lease-service owned."
                    )
            FreeCAD.closeDocument(doc_name)
            FreeCAD.Console.PrintMessage(f"Document '{doc_name}' closed via RPC.\n")
            return True
        except Exception as e:
            return str(e)

    def _snapshot_gui(self, doc_name: str):
        import os
        import tempfile
        import time

        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return {"ok": False, "error": f"Document '{doc_name}' not found."}
            if not hasattr(FreeCAD, "_mcp_snapshots"):
                FreeCAD._mcp_snapshots = []
            fd, path = tempfile.mkstemp(suffix=".FCStd", prefix="mcp_snap_")
            os.close(fd)
            try:
                doc.saveCopy(path)
            except Exception as e:
                try:
                    os.remove(path)
                except Exception:
                    pass
                return {"ok": False, "error": f"Failed to save snapshot: {e}"}
            sid = "snap-" + str(int(time.time() * 1000))
            FreeCAD._mcp_snapshots.append(
                {"id": sid, "path": path, "doc": doc.Name, "t": time.time()}
            )
            while len(FreeCAD._mcp_snapshots) > 5:
                old = FreeCAD._mcp_snapshots.pop(0)
                try:
                    os.remove(old["path"])
                except Exception:
                    pass
            return {
                "ok": True,
                "snapshot_id": sid,
                "doc": doc.Name,
                "count": len(FreeCAD._mcp_snapshots),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _restore_gui(self, doc_name: str, snapshot_id):
        import os

        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return {"ok": False, "error": f"Document '{doc_name}' not found."}
            identity = None
            active = None
            if document_lease_service is not None:
                try:
                    identity = document_identity_service.resolve(
                        {"document_name": doc_name}
                    )
                    active = document_lease_service.get(
                        {"document_session_uuid": identity.session_uuid}
                    )
                except Exception:
                    active = None
            snaps = getattr(FreeCAD, "_mcp_snapshots", [])
            target = None
            lease_snapshot_id = (
                active.get("document_state", {}).get("snapshot_id")
                if active is not None
                else None
            )
            if active is not None and (
                snapshot_id is None or snapshot_id == lease_snapshot_id
            ):
                if not lease_snapshot_id:
                    return {
                        "ok": False,
                        "error_code": "LEASE_BASELINE_SNAPSHOT_MISSING",
                        "error": "The active lease has no recovery baseline snapshot",
                    }
                target = {
                    "id": lease_snapshot_id,
                    "path": str(recovery_snapshot_path(lease_snapshot_id)),
                    "doc": doc_name,
                }
            elif snapshot_id:
                for s in snaps:
                    if s["id"] == snapshot_id:
                        target = s
                        break
                if target is None:
                    return {"ok": False, "error": f"Snapshot not found: {snapshot_id}"}
            else:
                if not snaps:
                    return {"ok": False, "error": "No snapshots available to restore"}
                target = snaps[-1]
            if str(target.get("doc") or "") != doc_name:
                return {
                    "ok": False,
                    "error_code": "SNAPSHOT_DOCUMENT_MISMATCH",
                    "error": "Snapshot belongs to a different document",
                }
            if not os.path.exists(target["path"]):
                return {
                    "ok": False,
                    "error": f"Snapshot file missing: {target['path']}",
                }
            if active is not None:
                result = restore_snapshot_in_place_gui(
                    doc,
                    target["path"],
                    expected_document_name=doc_name,
                    expected_source_path=identity.canonical_path,
                    validator=validate_document_invariants,
                )
                observed = document_identity_service.inspect_registered_document(
                    identity.session_uuid, doc
                )
                if (
                    observed.session_uuid != identity.session_uuid
                    or observed.comparison_key != identity.comparison_key
                    or observed.file_identity != identity.file_identity
                ):
                    raise RuntimeError(
                        "restored live document no longer matches its lease identity"
                    )
                return {
                    **result,
                    "restored_id": target["id"],
                    "doc": doc_name,
                    "new_doc": doc_name,
                    "document_session_uuid": identity.session_uuid,
                    "lease_preserved": True,
                    "count": len(snaps),
                }
            # Restore unleased compatibility snapshots in place as well.  A
            # close/open cycle changes FreeCAD's internal document name to the
            # temporary snapshot basename and creates an avoidable identity
            # gap.  ``Document.load`` preserves the existing proxy and name.
            cur = doc.Name
            result = restore_snapshot_in_place_gui(
                doc,
                target["path"],
                expected_document_name=cur,
                expected_source_path=str(getattr(doc, "FileName", "") or "") or None,
                validator=validate_document_invariants,
            )
            return {
                **result,
                "restored_id": target["id"],
                "doc": cur,
                "new_doc": cur,
                "count": len(snaps),
            }
        except Exception as e:
            return {
                "ok": False,
                "error_code": getattr(e, "code", "SNAPSHOT_RESTORE_FAILED"),
                "error": str(e),
            }

    def _solve_assembly_gui(self, doc_name: str, assembly_name: str):
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return {"ok": False, "error": f"Document '{doc_name}' not found."}
            asm = doc.getObject(assembly_name)
            if not asm:
                return {"ok": False, "error": f"Assembly '{assembly_name}' not found."}
            try:
                is_asm = asm.isDerivedFrom("Assembly::AssemblyObject")
            except Exception:
                is_asm = False
            if not is_asm:
                return {
                    "ok": False,
                    "error": f"Object '{assembly_name}' is not an Assembly::AssemblyObject.",
                }
            method = None
            status = None
            error = None
            try:
                if hasattr(asm, "solve"):
                    status = asm.solve()
                    method = "assembly.solve()"
            except Exception as e:
                error = str(e)
            if method is None:
                try:
                    import JointObject

                    JointObject.solveIfAllowed(asm, True)
                    method = "JointObject.solveIfAllowed"
                    status = "ok"
                except Exception as e:
                    error = str(e) if error is None else error + " | " + str(e)
            if method is None:
                try:
                    asm.Document.recompute()
                    method = "recompute"
                    status = "ok"
                except Exception as e:
                    return {
                        "ok": False,
                        "error": f"solve_assembly failed: {error} | {e}",
                    }
            try:
                doc.recompute()
            except Exception:
                pass
            return {
                "ok": True,
                "assembly": asm.Name,
                "method": method,
                "status": str(status) if status is not None else None,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}


def start_rpc_server(port=None):
    global rpc_server_thread, rpc_server_instance, gui_dispatcher, worker_manager
    global rpc_server_runtime_id, rpc_server_started_at, rpc_server_actual_endpoint
    global rpc_session_manager, rpc_request_replay_cache, rpc_runtime_manifest
    global document_identity_service, document_lease_service
    global save_service

    if rpc_server_instance:
        return "RPC Server already running."
    shutdown_requested.clear()

    app = QtWidgets.QApplication.instance()
    if app is None:
        return "RPC Server could not start: no Qt application is running."
    if QtCore.QThread.currentThread() != app.thread():
        return "RPC Server must be started from FreeCAD's GUI thread."
    try:
        parent = FreeCADGui.getMainWindow()
    except Exception:
        parent = None
    gui_dispatcher = GuiDispatcher(parent)

    settings = load_settings()
    configuration_error = settings.get("_configuration_error")
    if configuration_error:
        gui_dispatcher.deleteLater()
        gui_dispatcher = None
        return (
            "RPC Server refused invalid freecad_mcp_settings.json: "
            f"{configuration_error}"
        )
    if port is None:
        try:
            port = int(settings.get("rpc_port", 9875))
        except (TypeError, ValueError):
            port = 9875
    configure_parts_library_path(FreeCAD.getUserAppDataDir())
    remote_enabled = settings.get("remote_enabled", False)
    allowed_ips = settings.get("allowed_ips", "127.0.0.1")
    version = _freecad_version_parts()[:4]
    while len(version) < 4:
        version += ("",)
    worker_manager = WorkerManager(
        WorkerRuntime(
            gui_executable=sys.executable,
            freecad_home=(
                FreeCAD.getHomePath()
                if callable(getattr(FreeCAD, "getHomePath", None))
                else os.path.dirname(sys.executable)
            ),
            gui_version=version,
            configured_path=settings.get("freecadcmd_path", ""),
        ),
        os.path.dirname(__file__),
    )

    lease_mode = settings.get("document_lease_mode", "off")
    try:
        initialize_document_lease_runtime(settings)
    except Exception as exc:
        gui_dispatcher.deleteLater()
        gui_dispatcher = None
        worker_manager = None
        return f"RPC Server refused document lease runtime configuration: {exc}"
    try:
        host = resolve_rpc_bind_host(settings)
    except SettingsPolicyError as exc:
        gui_dispatcher.deleteLater()
        gui_dispatcher = None
        worker_manager = None
        return f"RPC Server refused unsafe configuration: {exc}"

    rpc_server_instance = FilteredXMLRPCServer(
        (host, port), allowed_ips_str=allowed_ips, allow_none=True, logRequests=False
    )
    actual_host, actual_port = rpc_server_instance.server_address[:2]
    rpc_server_actual_endpoint = {"host": actual_host, "port": int(actual_port)}
    rpc_server_runtime_id = _ADDON_RUNTIME_ID
    rpc_server_started_at = (
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )

    profile_id = str(
        settings.get("profile_instance_id") or settings.get("instance_id") or ""
    )
    auth_secret_file = str(settings.get("auth_secret_file") or "")
    valid_profile_uuid = False
    if profile_id:
        try:
            uuid.UUID(profile_id)
            valid_profile_uuid = True
        except (ValueError, AttributeError):
            pass
    if lease_mode == "enforce" and (
        not profile_id or not valid_profile_uuid or not auth_secret_file
    ):
        rpc_server_instance.server_close()
        rpc_server_instance = None
        gui_dispatcher.deleteLater()
        gui_dispatcher = None
        worker_manager = None
        rpc_server_runtime_id = ""
        rpc_server_started_at = ""
        rpc_server_actual_endpoint = None
        return (
            "RPC Server refused enforce mode because a UUID profile_instance_id "
            "and auth_secret_file are required"
        )

    if lease_mode != "off":
        # Runtime initialization precedes listener binding and is retained
        # across Stop/Start. Refresh aliases for documents opened since the
        # addon's startup callback ran.
        try:
            for document in FreeCAD.listDocuments().values():
                _ensure_v2_document(document)
        except Exception as exc:
            logger.warning("Could not register all live document identities: %s", exc)
    else:
        # Downgrading the listener must never discard live lease authority.
        # With no records the dormant runtime is harmless and preserves open
        # document UUIDs should lease mode be enabled again later.
        active_records = (
            document_lease_service.list_records()
            if document_lease_service is not None
            else []
        )
        if active_records:
            rpc_server_instance.server_close()
            rpc_server_instance = None
            gui_dispatcher.deleteLater()
            gui_dispatcher = None
            worker_manager = None
            rpc_server_runtime_id = ""
            rpc_server_started_at = ""
            rpc_server_actual_endpoint = None
            return (
                "RPC Server refused document_lease_mode=off while active v2 "
                "lease or recovery records exist"
            )

    rpc_session_manager = None
    rpc_runtime_manifest = None
    if profile_id and auth_secret_file:
        try:
            secret = load_profile_secret(auth_secret_file)
            lease_runtime = _require_authenticated_lease_runtime(profile_id)
            version_parts = list(_freecad_version_parts())
            freecad_version_text = ".".join(version_parts[:3]) or "unknown"
            freecad_revision = (
                version_parts[3]
                if len(version_parts) > 3 and version_parts[3]
                else "unknown"
            )
            rpc_runtime_manifest = make_runtime_manifest(
                profile_id=profile_id,
                addon_runtime_id=lease_runtime.addon_runtime_id,
                freecad_pid=lease_runtime.freecad_pid,
                freecad_process_started_at=(lease_runtime.freecad_process_started_at),
                boot_id=lease_runtime.boot_id,
                rpc_host=str(actual_host),
                rpc_port=int(actual_port),
                freecad_version=freecad_version_text,
                freecad_revision=freecad_revision,
                addon_version="0.1.20",
                addon_build_id="freecad-mcp-addon-0.1.20",
                profile_path_fingerprint=_profile_fingerprint(),
            )
            rpc_session_manager = SessionManager(
                manifest=rpc_runtime_manifest, secret=secret
            )
            rpc_request_replay_cache.set_owner_lease_predicate(
                document_lease_service.has_unresolved_owner
            )
        except Exception as exc:
            logger.error("Could not initialize authenticated RPC v2: %s", exc)
            if lease_mode == "enforce":
                rpc_server_instance.server_close()
                rpc_server_instance = None
                gui_dispatcher.deleteLater()
                gui_dispatcher = None
                worker_manager = None
                rpc_server_runtime_id = ""
                rpc_server_started_at = ""
                rpc_server_actual_endpoint = None
                return "RPC Server could not initialize authenticated lease protocol"

    rpc_server_instance.register_instance(
        FreeCADRPC(
            allow_execute_code=(
                not remote_enabled
                or bool(settings.get("allow_remote_execute_code", False))
            )
        )
    )

    def server_loop():
        logger.info("RPC Server started at %s:%s", actual_host, actual_port)
        if remote_enabled:
            logger.info("Remote connections enabled. Allowed IPs: %s", allowed_ips)
        rpc_server_instance.serve_forever()

    rpc_server_thread = threading.Thread(target=server_loop, daemon=True)
    rpc_server_thread.start()

    msg = f"RPC Server started at {actual_host}:{actual_port}."
    if remote_enabled:
        msg += f" Allowed IPs: {allowed_ips}"
    return msg


def stop_rpc_server():
    global rpc_server_instance, rpc_server_thread, gui_dispatcher, worker_manager
    global rpc_server_runtime_id, rpc_server_started_at, rpc_server_actual_endpoint
    global rpc_session_manager, rpc_request_replay_cache, rpc_runtime_manifest
    global document_identity_service, document_lease_service
    global save_service

    if rpc_server_instance:
        shutdown_requested.set()
        server = rpc_server_instance
        thread = rpc_server_thread
        cancelling_rpc = FreeCADRPC()
        cancellation_deadline = (
            time.monotonic() + RPC_SHUTDOWN_CANCELLATION_WAIT_SECONDS
        )
        for inflight in rpc_inflight_request_registry.request_cancel_all():
            try:
                remaining = max(0.0, cancellation_deadline - time.monotonic())
                fenced = cancelling_rpc._begin_request_cancellation(
                    inflight, wait_timeout=remaining
                )
                if fenced is None:
                    logger.error(
                        "Cancellation fence for request %s is still owned by "
                        "another phase; retaining its active lease/error fence",
                        inflight.request_id,
                    )
            except Exception:
                logger.exception(
                    "Could not fence request %s during RPC shutdown",
                    inflight.request_id,
                )
        if gui_dispatcher is not None:
            gui_dispatcher.stop_accepting()

        completed = threading.Event()

        def _shutdown():
            try:
                server.begin_shutdown()
                if worker_manager is not None:
                    worker_manager.stop(timeout=4.0)
                server.shutdown()
                server.server_close()
                if thread is not None:
                    thread.join(timeout=2.0)
            finally:
                completed.set()

        threading.Thread(target=_shutdown, daemon=True).start()
        completed.wait(timeout=2.5)
        rpc_server_instance = None
        rpc_server_thread = None
        dispatcher = gui_dispatcher
        gui_dispatcher = None
        worker_manager = None
        rpc_server_runtime_id = ""
        rpc_server_started_at = ""
        rpc_server_actual_endpoint = None
        rpc_session_manager = None
        rpc_runtime_manifest = None
        if dispatcher is not None:
            dispatcher.deleteLater()
        logger.info("RPC Server stopped")
        if completed.is_set():
            return "RPC Server stopped."
        return "RPC Server shutdown is continuing in the background."

    return "RPC Server was not running."


from .commands import register_commands, schedule_toggle_sync  # noqa: E402


register_commands()
schedule_toggle_sync()
