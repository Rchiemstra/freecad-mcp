import FreeCAD
import FreeCADGui
import ObjectsFem

import contextlib
import ipaddress
import json
import logging
import re
import base64
import io
import os
import sys
import tempfile
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any
from xmlrpc.client import Fault, dumps as xmlrpc_dumps, loads as xmlrpc_loads
from xmlrpc.server import SimpleXMLRPCRequestHandler, SimpleXMLRPCServer

from PySide import QtCore, QtWidgets

from .execution_safety import (
    RequestClass,
    classify_execute_code,
    find_gui_blocking_risk,
    find_gui_geometry_loop_risk,
)
from .gui_dispatcher import GuiDispatchError, GuiDispatcher
from .parts_library import (
    configure_parts_library_path,
    get_parts_list,
    insert_part_from_library,
)
from .reference_repair import inspect_references_gui, repair_references_gui
from .serialize import serialize_object
from .snapshot_service import create_primary_snapshot_gui
from .view_manager import (
    animate_object_placement,
    build_orbit_frames,
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
shutdown_requested = threading.Event()
logger = logging.getLogger("FreeCADMCP.rpc_server")


# --- Settings persistence ---

_SETTINGS_FILENAME = "freecad_mcp_settings.json"

_DEFAULT_SETTINGS = {
    "remote_enabled": False,
    "allowed_ips": "127.0.0.1",
    "auto_start_rpc": False,
    "rpc_port": 9875,
    "freecadcmd_path": "",
    "allow_remote_execute_code": False,
    # Stable identity for this addon instance/profile. Empty on the default
    # profile; the isolated-profile setup writes a unique value so a client can
    # verify it reached the intended instance (see get_instance_info).
    "instance_id": "",
    # Per-document agent write leases (default off — production untouched).
    "enable_document_lock": False,
    "document_lock_enforcement": False,
}


def _get_settings_path():
    return os.path.join(FreeCAD.getUserAppDataDir(), _SETTINGS_FILENAME)


def load_settings():
    path = _get_settings_path()
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                settings = json.load(f)
            # Ensure all default keys exist
            for key, value in _DEFAULT_SETTINGS.items():
                if key not in settings:
                    settings[key] = value
            return settings
        except Exception as e:
            FreeCAD.Console.PrintWarning(f"Failed to load MCP settings: {e}\n")
    return dict(_DEFAULT_SETTINGS)


def save_settings(settings):
    path = _get_settings_path()
    try:
        with open(path, "w") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        FreeCAD.Console.PrintError(f"Failed to save MCP settings: {e}\n")


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
            document_lock.set_request_identity(
                instance_id=headers.get("X-MCP-Instance-Id") or None,
                client=headers.get("X-MCP-Client") or None,
                pid=pid,
                host=headers.get("X-MCP-Host") or None,
                lease_token=headers.get("X-MCP-Lease-Token") or None,
                rpc_port=rpc_port,
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

class FilteredXMLRPCServer(SimpleXMLRPCServer):
    """IP-filtered server with separate bounded general/control capacity."""

    CONTROL_METHODS = frozenset({
        "ping",
        "get_worker_status",
        "cancel_worker_job",
        "shutdown_rpc_server",
    })

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
            return super()._marshaled_dispatch(data, dispatch_method, path)
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
                            raise ValueError(f"Referenced object '{ref_name}' not found.")
                    setattr(obj, prop, refs)

                else:
                    setattr(obj, prop, val)
            # ShapeColor is a property of the ViewObject
            elif prop == "ShapeColor" and isinstance(val, (list, tuple)):
                setattr(obj.ViewObject, prop, (float(val[0]), float(val[1]), float(val[2]), float(val[3])))

            elif prop == "ViewObject" and isinstance(val, dict):
                for k, v in val.items():
                    if k == "ShapeColor":
                        setattr(obj.ViewObject, k, (float(v[0]), float(v[1]), float(v[2]), float(v[3])))
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

    def _dispatch(self, method, params):
        """XML-RPC chokepoint: enforce document leases when configured.

        When ``document_lock_enforcement`` is off, behaviour is identical to
        the default SimpleXMLRPCDispatcher instance dispatch.
        """
        try:
            dl = _import_document_lock()
            VerbKind = dl.VerbKind
            annotate_read_result = dl.annotate_read_result
            begin_agent_mutation = dl.begin_agent_mutation
            check_mutation_allowed = dl.check_mutation_allowed
            classify_verb = dl.classify_verb
            end_agent_mutation = dl.end_agent_mutation
            extract_referenced_documents_from_code = dl.extract_referenced_documents_from_code
            is_enforcement_enabled = dl.is_enforcement_enabled
            resolve_doc_key = dl.resolve_doc_key
        except ImportError:
            func = getattr(self, method, None)
            if func is None or method.startswith("_"):
                raise Exception(f'method "{method}" is not supported')
            return func(*params)

        kind, extractor = classify_verb(method)
        enforce = is_enforcement_enabled()

        # Resolve callable first (also validates method exists)
        func = getattr(self, method, None)
        if func is None or method.startswith("_"):
            raise Exception(f'method "{method}" is not supported')

        if not enforce:
            return func(*params)

        # --- Enforcement path ---
        doc_name = None
        try:
            doc_name = extractor(params if isinstance(params, tuple) else tuple(params))
        except Exception:
            doc_name = None

        # execute_code / async: explicit document + multi-doc guards
        if method == "execute_code":
            options = params[1] if len(params) > 1 and isinstance(params[1], dict) else {}
            read_only = bool(options.get("read_only", False))
            code = params[0] if params else ""
            if not read_only:
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
                additional = list(options.get("additional_documents") or [])
                referenced = extract_referenced_documents_from_code(code)
                declared = {primary, *additional}
                undeclared = referenced - declared
                if undeclared:
                    return {
                        "success": False,
                        "error_code": "multi_document_undeclared",
                        "error": (
                            "execute_code references documents not declared in "
                            f"options.document / additional_documents: {sorted(undeclared)}. "
                            "Declare and lock every affected document."
                        ),
                        "undeclared": sorted(undeclared),
                    }
                for name in declared:
                    try:
                        key = resolve_doc_key(doc_name=name)
                    except Exception as exc:
                        return {
                            "success": False,
                            "error_code": "document_not_locked",
                            "error": f"Cannot resolve document {name!r}: {exc}",
                        }
                    allowed = check_mutation_allowed(key)
                    if not allowed.get("success"):
                        return allowed
                # Run with agent-mutating flags set for all declared docs
                keys = []
                for name in declared:
                    try:
                        keys.append(resolve_doc_key(doc_name=name))
                    except Exception:
                        pass
                for key in keys:
                    begin_agent_mutation(key)
                # Also flag by doc name for observer matching
                for name in declared:
                    begin_agent_mutation(name)
                try:
                    return func(*params)
                finally:
                    for key in keys:
                        end_agent_mutation(key)
                    for name in declared:
                        end_agent_mutation(name)

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
        allowed = check_mutation_allowed(doc_key)
        if not allowed.get("success"):
            return allowed

        begin_agent_mutation(doc_key)
        begin_agent_mutation(doc_name)
        try:
            result = func(*params)
            # Keep lock on failure; mark LOCKED_ERROR when structured failure
            if isinstance(result, dict) and (
                result.get("success") is False or result.get("ok") is False
            ):
                try:
                    dl = _import_document_lock()
                    lease = dl.get_lease(doc_key)
                    if lease is not None:
                        dl.heartbeat_lease(
                            doc_key,
                            lease.token,
                            state=dl.LeaseState.LOCKED_ERROR.value,
                            current_operation=f"error:{method}",
                        )
                except Exception:
                    pass
            return result
        finally:
            end_agent_mutation(doc_key)
            end_agent_mutation(doc_name)

    def _dispatch_gui(self, task, timeout=None):
        """Run *task* on the GUI thread and preserve legacy string errors."""
        dispatcher = gui_dispatcher
        if dispatcher is None:
            return "RPC GUI dispatcher is not initialized"
        t = timeout if timeout is not None else self.TIMEOUT
        try:
            return dispatcher.submit(task, t)
        except GuiDispatchError as exc:
            logger.error("RPC GUI dispatch failed: %s", exc)
            return str(exc)

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

    def ping(self):
        return True

    # --- Document lock verbs -------------------------------------------------

    def acquire_document_lock(
        self,
        doc_name: str = "",
        file_path: str = "",
        session_id: str = "",
        task_description: str = "",
        client: str = "",
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
        if not (doc_name or file_path or session_id):
            return {
                "success": False,
                "error_code": "document_identity_required",
                "error": (
                    "Provide an explicit doc_name, file_path, or session_id "
                    "(never implicitly locks ActiveDocument)"
                ),
            }

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
                dirty = bool(getattr(doc, "Modified", False))
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
        if not (doc_name or file_path or session_id):
            return {
                "success": False,
                "error_code": "document_identity_required",
                "error": "Provide doc_name, file_path, or session_id",
            }
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
        return {"success": True, "locked": True, "doc_key": key, "lease": lease.to_dict()}

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
        result = dl.heartbeat_lease(
            doc_key,
            token,
            current_operation=current_operation or None,
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

    def release_document_lock(self, doc_key: str, token: str) -> dict[str, Any]:
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
        result = dl.release_lease(doc_key, token)
        if result.get("success"):
            try:
                from lock_indicator import refresh_lock_indicator

                refresh_lock_indicator()
            except Exception:
                pass
        return result

    def force_release_stale_lock(self, doc_key: str) -> dict[str, Any]:
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
        result = dl.force_release_stale_lock(doc_key)
        if result.get("success"):
            try:
                from lock_indicator import refresh_lock_indicator

                refresh_lock_indicator()
            except Exception:
                pass
        return result

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
        return {
            "ok": True,
            "instance_id": settings.get("instance_id", "") or "",
            "pid": os.getpid(),
            "port": settings.get("rpc_port", 9875),
            "profile_path": profile_path,
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

    def edit_object(self, doc_name: str, obj_name: str, properties: dict[str, Any]) -> dict[str, Any]:
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
                        entries.append({
                            "name": obj.Name,
                            "label": getattr(obj, "Label", obj.Name),
                            "state": state,
                        })
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
            _key(doc, item["name"])
            for doc, items in before.items()
            for item in items
        }
        target_errors: list[dict[str, Any]] = []
        pre_existing: list[dict[str, Any]] = []
        unrelated: list[dict[str, Any]] = []
        for doc, items in after.items():
            for item in items:
                entry = {"document": doc, "object": item["name"], "state": item["state"]}
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

    def execute_code(self, code: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
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
        classification = classify_execute_code(
            code, read_only=bool(options.get("read_only", False))
        )
        use_worker = execution_mode == "worker" or (
            execution_mode == "auto"
            and bool(options.get("read_only", False))
            and classification in (RequestClass.WORKER_ANALYSIS, RequestClass.UNKNOWN)
        )
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
        block_unmarked_mutation = execution_mode == "auto" and not read_only
        block_forced_gui_analysis = execution_mode == "gui" and read_only
        if loop_risk is not None and (
            block_unmarked_mutation or block_forced_gui_analysis
        ):
            if block_forced_gui_analysis:
                guidance = (
                    "Read-only geometry loops cannot be forced onto the GUI thread. "
                    "Use execution_mode='auto' or 'worker' so the analysis runs in "
                    "an isolated FreeCADCmd process with a hard timeout."
                )
            else:
                guidance = (
                    "For analysis, set read_only=true and execution_mode='worker' "
                    "with a hard timeout. For an intentional document mutation, "
                    "split the work into bounded chunks or explicitly set "
                    "execution_mode='gui'."
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

            active_before = FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None
            dirty_before = {
                name: bool(getattr(doc, "Modified", False))
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
            active_after = FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None
            dirty_after = {
                name: bool(getattr(doc, "Modified", False))
                for name, doc in FreeCAD.listDocuments().items()
            }
            target_doc_obj = FreeCAD.getDocument(target_doc) if target_doc else None
            session = {
                "active_document_before": active_before,
                "active_document_after": active_after,
                "dirty_before": dirty_before,
                "dirty_after": dirty_after,
                "saved": False,
                "file_path": getattr(target_doc_obj, "FileName", "") if target_doc_obj else "",
                **classified,
            }
            if read_only_unguarded:
                session["read_only_unguarded_documents"] = read_only_unguarded
            if ok:
                return {"ok": True, "session": session, "stdout": output_buffer.getvalue()}
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
                    flat_errors.append({
                        "doc": item.get("document") or options.get("document") or "?",
                        "name": item.get("object", "?"),
                        "state": item.get("state", []),
                    })
            return {
                "success": True,
                "message": "Python code execution completed.\nOutput: " + res.get("stdout", ""),
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

    def _execute_code_worker(self, code: str, options: dict[str, Any]) -> dict[str, Any]:
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
                if snapshot.get("error_code") != "snapshot_state_changed" or attempt == 1:
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

    def insert_part_from_library(self, relative_path):
        res = self._dispatch_gui(lambda: self._insert_part_from_library(relative_path))
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

        res = self._dispatch_gui(lambda: _open_document(path))
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

    def run_fem_analysis(self, doc_name: str, analysis_name: str, timeout: int = 600) -> dict[str, Any]:
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
            self._dispatch_gui(lambda: FreeCADGui.getMainWindow().statusBar().showMessage(msg))

        def _clear_status():
            self._dispatch_gui(lambda: FreeCADGui.getMainWindow().statusBar().clearMessage())

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
                FreeCAD.Console.PrintError(
                    f"Async code error: {e}\n{_tb.format_exc()}"
                )
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
                has_save_image = hasattr(active_view, 'saveImage')
                FreeCAD.Console.PrintMessage(f"View type: {view_type}, Has saveImage: {has_save_image}\n")
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
                        elevation_yaw_start_deg=float(orbit.get("yaw_start_deg") or 0.0),
                    )
                )
            if frames:
                work_frames.extend(frames)
            if not work_frames:
                return {"ok": False, "error": "Provide frames and/or orbit", "frames": []}

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
                        payload["image_base64"] = base64.b64encode(handle.read()).decode("utf-8")
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
            ok_count = sum(1 for frame in encoded_frames if frame["ok"] and frame["image_base64"])
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
                        elevation_yaw_start_deg=float(orbit.get("yaw_start_deg") or 0.0),
                    )
                )
            if frames:
                work_frames.extend(frames)
            if not work_frames:
                return {"ok": False, "error": "Provide frames and/or orbit", "frame_paths": []}
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
                touch_objects=touch_objects,
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
                        result["image_base64"] = base64.b64encode(handle.read()).decode("utf-8")
                else:
                    result["capture_error"] = str(status)
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            return result

        try:
            return self._dispatch_gui(_run)
        except Exception as exc:
            logger.exception("refresh_view failed")
            return {"ok": False, "error": str(exc)}

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
                        payload["image_base64"] = base64.b64encode(handle.read()).decode("utf-8")
                encoded_frames.append(payload)
            result["frames"] = encoded_frames
            return result

        try:
            return self._dispatch_gui(_run)
        except Exception as exc:
            logger.exception("animate_placement failed")
            return {"ok": False, "error": str(exc)}

    def sketch_create(self, doc_name: str, sketch_name: str, body_name: str | None = None, attach_to: str | None = None) -> dict:
        res = self._dispatch_gui(lambda: self._sketch_create_gui(doc_name, sketch_name, body_name, attach_to))
        if res is True:
            return {"success": True, "sketch_name": sketch_name}
        return {"success": False, "error": res}

    def sketch_add_geometry(self, doc_name: str, sketch_name: str, geometry: list) -> dict:
        res = self._dispatch_gui(lambda: self._sketch_add_geometry_gui(doc_name, sketch_name, geometry))
        if isinstance(res, list):
            return {"success": True, "indices": res}
        return {"success": False, "error": res}

    def sketch_add_constraint(self, doc_name: str, sketch_name: str, constraints: list) -> dict:
        res = self._dispatch_gui(lambda: self._sketch_add_constraint_gui(doc_name, sketch_name, constraints))
        if res is True:
            return {"success": True}
        return {"success": False, "error": res}

    def pad_feature(self, doc_name: str, sketch_name: str, pad_name: str, length: float, body_name: str | None = None, symmetric: bool = False, reversed_dir: bool = False) -> dict:
        res = self._dispatch_gui(lambda: self._pad_feature_gui(doc_name, sketch_name, pad_name, length, body_name, symmetric, reversed_dir))
        if res is True:
            return {"success": True, "pad_name": pad_name}
        return {"success": False, "error": res}

    def pocket_feature(self, doc_name: str, sketch_name: str, pocket_name: str, length: float, body_name: str | None = None, symmetric: bool = False, reversed_dir: bool = False) -> dict:
        res = self._dispatch_gui(lambda: self._pocket_feature_gui(doc_name, sketch_name, pocket_name, length, body_name, symmetric, reversed_dir))
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
        res = self._dispatch_gui(lambda: self._spreadsheet_create_gui(doc_name, sheet_name))
        return res if isinstance(res, dict) else {"success": False, "error": res}

    def spreadsheet_set_cells(self, doc_name: str, sheet_name: str, cells: list) -> dict:
        res = self._dispatch_gui(lambda: self._spreadsheet_set_cells_gui(doc_name, sheet_name, cells))
        return res if isinstance(res, dict) else {"success": False, "error": res}

    def spreadsheet_get_cells(self, doc_name: str, sheet_name: str, addresses: list) -> dict:
        res = self._dispatch_gui(lambda: self._spreadsheet_get_cells_gui(doc_name, sheet_name, addresses))
        return res if isinstance(res, dict) else {"success": False, "error": res}

    def spreadsheet_set_alias(self, doc_name: str, sheet_name: str, address: str, alias: str) -> dict:
        res = self._dispatch_gui(lambda: self._spreadsheet_set_alias_gui(doc_name, sheet_name, address, alias))
        return res if isinstance(res, dict) else {"success": False, "error": res}

    def spreadsheet_list_aliases(self, doc_name: str, sheet_name: str) -> dict:
        res = self._dispatch_gui(lambda: self._spreadsheet_list_aliases_gui(doc_name, sheet_name))
        return res if isinstance(res, dict) else {"success": False, "error": res}

    def set_expression(self, doc_name: str, object_name: str, prop_path: str, expression: str) -> dict:
        res = self._dispatch_gui(lambda: self._set_expression_gui(doc_name, object_name, prop_path, expression))
        return res if isinstance(res, dict) else {"success": False, "error": res}

    def clear_expression(self, doc_name: str, object_name: str, prop_path: str) -> dict:
        res = self._dispatch_gui(lambda: self._clear_expression_gui(doc_name, object_name, prop_path))
        return res if isinstance(res, dict) else {"success": False, "error": res}

    def list_expressions(self, doc_name: str, object_name: str) -> dict:
        res = self._dispatch_gui(lambda: self._list_expressions_gui(doc_name, object_name))
        return res if isinstance(res, dict) else {"success": False, "error": res}

    def body_create(self, doc_name: str, body_name: str) -> dict:
        res = self._dispatch_gui(lambda: self._body_create_gui(doc_name, body_name))
        return res if isinstance(res, dict) else {"success": False, "error": res}

    def body_set_tip(self, doc_name: str, body_name: str, feature_name: str) -> dict:
        res = self._dispatch_gui(lambda: self._body_set_tip_gui(doc_name, body_name, feature_name))
        return res if isinstance(res, dict) else {"success": False, "error": res}

    def sketch_attach(self, doc_name: str, sketch_name: str, support) -> dict:
        res = self._dispatch_gui(lambda: self._sketch_attach_gui(doc_name, sketch_name, support))
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
            lambda: self._sketch_edit_constraint_gui(doc_name, sketch_name, value, name, index)
        )
        return res if isinstance(res, dict) else {"success": False, "error": res}

    def diagnose_parametric(self, doc_name: str, object_name=None) -> dict:
        res = self._dispatch_gui(lambda: self._diagnose_parametric_gui(doc_name, object_name))
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
                            exprs.append({"prop": str(item[0]), "expression": str(item[1])})
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
            "constraint_count": len(sk.Constraints) if hasattr(sk, "Constraints") else 0,
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
        res = self._dispatch_gui(lambda: self._solve_assembly_gui(doc_name, assembly_name))
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
                results.append({
                    "Name": getattr(obj, "Name", "<unknown>"),
                    "Label": getattr(obj, "Label", "<unknown>"),
                    "TypeId": getattr(obj, "TypeId", "<unknown>"),
                    "error": f"Serialization failed: {e}",
                })
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
                    res = getattr(doc, obj.analysis).addObject(ObjectsFem.makeMeshGmsh(doc, obj.name))[0]
                    if "Part" in obj.properties:
                        target_obj = doc.getObject(obj.properties["Part"])
                        if target_obj:
                            res.Part = target_obj
                        else:
                            raise ValueError(f"Referenced object '{obj.properties['Part']}' not found.")
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
                    make_method = fem_make_methods.get(obj_type_short, getattr(ObjectsFem, method_name, None))

                    if callable(make_method):
                        res = make_method(doc, obj.name)
                        set_object_property(doc, res, obj.properties)
                        FreeCAD.Console.PrintMessage(
                            f"FEM object '{res.Name}' created with '{method_name}'.\n"
                        )
                    else:
                        raise ValueError(f"No creation method '{method_name}' found in ObjectsFem.")
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
            FreeCAD.Console.PrintError(f"Object '{obj.name}' not found in document '{doc_name}'.\n")
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

    def _insert_part_from_library(self, relative_path):
        try:
            insert_part_from_library(relative_path)
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
        # Close, then reopen from the same file. Reopen preserves the
        # original document name when the file was previously saved
        # under that name.
        FreeCAD.closeDocument(doc_name)
        FreeCAD.openDocument(file_path)
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
            FreeCAD.Console.PrintMessage(f"Sketch '{sketch_name}' created in '{doc_name}'.\n")
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
                    pt = Part.Point(FreeCAD.Vector(geom.get("x", 0), geom.get("y", 0), 0))
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
                    idx = sketch.addConstraint(Sketcher.Constraint("Coincident", c["geo1"], c["pos1"], c["geo2"], c["pos2"]))
                elif t == "Horizontal":
                    idx = sketch.addConstraint(Sketcher.Constraint("Horizontal", c["geo"]))
                elif t == "Vertical":
                    idx = sketch.addConstraint(Sketcher.Constraint("Vertical", c["geo"]))
                elif t == "Distance":
                    if "geo2" in c:
                        idx = sketch.addConstraint(Sketcher.Constraint("Distance", c["geo1"], c.get("pos1", 0), c["geo2"], c.get("pos2", 0), c["value"]))
                    elif "pos" in c:
                        idx = sketch.addConstraint(Sketcher.Constraint("Distance", c["geo"], c["pos"], c["value"]))
                    else:
                        idx = sketch.addConstraint(Sketcher.Constraint("Distance", c["geo"], c["value"]))
                elif t == "DistanceX":
                    if "pos" in c:
                        idx = sketch.addConstraint(Sketcher.Constraint("DistanceX", c["geo"], c["pos"], c["value"]))
                    else:
                        idx = sketch.addConstraint(Sketcher.Constraint("DistanceX", c["geo"], c["value"]))
                elif t == "DistanceY":
                    if "pos" in c:
                        idx = sketch.addConstraint(Sketcher.Constraint("DistanceY", c["geo"], c["pos"], c["value"]))
                    else:
                        idx = sketch.addConstraint(Sketcher.Constraint("DistanceY", c["geo"], c["value"]))
                elif t == "Radius":
                    idx = sketch.addConstraint(Sketcher.Constraint("Radius", c["geo"], c["value"]))
                elif t == "Diameter":
                    idx = sketch.addConstraint(Sketcher.Constraint("Diameter", c["geo"], c["value"]))
                elif t == "Angle":
                    if "geo2" in c:
                        idx = sketch.addConstraint(Sketcher.Constraint("Angle", c["geo1"], c.get("pos1", 0), c["geo2"], c.get("pos2", 0), c["value"]))
                    else:
                        idx = sketch.addConstraint(Sketcher.Constraint("Angle", c["geo"], c["value"]))
                elif t == "Parallel":
                    idx = sketch.addConstraint(Sketcher.Constraint("Parallel", c["geo1"], c["geo2"]))
                elif t == "Perpendicular":
                    idx = sketch.addConstraint(Sketcher.Constraint("Perpendicular", c["geo1"], c["geo2"]))
                elif t == "Equal":
                    idx = sketch.addConstraint(Sketcher.Constraint("Equal", c["geo1"], c["geo2"]))
                elif t == "Symmetric":
                    idx = sketch.addConstraint(Sketcher.Constraint("Symmetric", c["geo1"], c["pos1"], c["geo2"], c["pos2"], c["geo3"], c.get("pos3", 0)))
                elif t == "PointOnObject":
                    idx = sketch.addConstraint(Sketcher.Constraint("PointOnObject", c["geo1"], c["pos1"], c["geo2"]))
                elif t == "Tangent":
                    idx = sketch.addConstraint(Sketcher.Constraint("Tangent", c["geo1"], c["geo2"]))
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
            return {"success": True, "sheet": sheet.Name, "address": address, "alias": alias}
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
            return {"success": True, "object": obj.Name, "expressions": exprs, "count": len(exprs)}
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
            return {"success": True, "body": body.Name, "tip": getattr(tip, "Name", None)}
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
                        if getattr(obj, "TypeId", "") == "PartDesign::Body" and sketch in getattr(obj, "Group", []):
                            body = obj
                            break
                    origins = []
                    if body is not None and getattr(body, "Origin", None) is not None:
                        origins.append(body.Origin)
                    for o in doc.Objects:
                        if getattr(o, "TypeId", "") == "App::Origin" and o not in origins:
                            origins.append(o)
                    for origin in origins:
                        for feat in getattr(origin, "OriginFeatures", []) or []:
                            if getattr(feat, "Label", "") == support or getattr(feat, "Name", "") == support:
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
                    attached = {"object": plane.Name, "subname": "", "kind": "origin_plane", "plane": support}
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
                    invalid.append({
                        "name": obj.Name,
                        "label": getattr(obj, "Label", obj.Name),
                        "type": getattr(obj, "TypeId", ""),
                        "state": state,
                    })
                for item in getattr(obj, "ExpressionEngine", None) or []:
                    try:
                        prop = str(item[0]) if isinstance(item, (list, tuple)) and len(item) >= 1 else "?"
                        expr = str(item[1]) if isinstance(item, (list, tuple)) and len(item) >= 2 else str(item)
                        bound = obj.getExpression(prop) if hasattr(obj, "getExpression") else None
                        if bound is None and expr:
                            expression_issues.append({
                                "object": obj.Name,
                                "prop": prop,
                                "expression": expr,
                                "issue": "missing_binding",
                            })
                    except Exception as e:
                        expression_issues.append({
                            "object": obj.Name,
                            "issue": "expression_error",
                            "message": str(e),
                        })
                if getattr(obj, "TypeId", "") == "Sketcher::SketchObject":
                    sketches.append({
                        "name": obj.Name,
                        "geometry_count": len(getattr(obj, "Geometry", []) or []),
                        "constraint_count": len(getattr(obj, "Constraints", []) or []),
                        "state": state,
                        "conflicting": list(getattr(obj, "ConflictingConstraints", []) or []),
                        "redundant": list(getattr(obj, "RedundantConstraints", []) or []),
                        "malformed": list(getattr(obj, "MalformedConstraints", []) or []),
                    })
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

    def _pad_feature_gui(self, doc_name, sketch_name, pad_name, length, body_name, symmetric, reversed_dir):
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

    def _pocket_feature_gui(self, doc_name, sketch_name, pocket_name, length, body_name, symmetric, reversed_dir):
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
            FreeCAD.Console.PrintMessage(f"Pocket '{pocket_name}' created in '{doc_name}'.\n")
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
                doc.save(path)
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
            return {"ok": True, "snapshot_id": sid, "doc": doc.Name,
                    "count": len(FreeCAD._mcp_snapshots)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _restore_gui(self, doc_name: str, snapshot_id):
        import os
        try:
            doc = FreeCAD.getDocument(doc_name)
            if not doc:
                return {"ok": False, "error": f"Document '{doc_name}' not found."}
            snaps = getattr(FreeCAD, "_mcp_snapshots", [])
            if not snaps:
                return {"ok": False, "error": "No snapshots available to restore"}
            target = None
            if snapshot_id:
                for s in snaps:
                    if s["id"] == snapshot_id:
                        target = s
                        break
                if target is None:
                    return {"ok": False, "error": f"Snapshot not found: {snapshot_id}"}
            else:
                target = snaps[-1]
            if not os.path.exists(target["path"]):
                return {"ok": False, "error": f"Snapshot file missing: {target['path']}"}
            cur = doc.Name
            try:
                FreeCAD.closeDocument(cur)
            except Exception:
                pass
            restored = FreeCAD.open(target["path"])
            return {"ok": True, "restored_id": target["id"], "doc": cur,
                    "new_doc": restored.Name if restored is not None else cur,
                    "count": len(snaps)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

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
                return {"ok": False, "error": f"Object '{assembly_name}' is not an Assembly::AssemblyObject."}
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
                    error = (str(e) if error is None else error + " | " + str(e))
            if method is None:
                try:
                    asm.Document.recompute()
                    method = "recompute"
                    status = "ok"
                except Exception as e:
                    return {"ok": False, "error": f"solve_assembly failed: {error} | {e}"}
            try:
                doc.recompute()
            except Exception:
                pass
            return {"ok": True, "assembly": asm.Name, "method": method,
                    "status": str(status) if status is not None else None}
        except Exception as e:
            return {"ok": False, "error": str(e)}


def start_rpc_server(port=None):
    global rpc_server_thread, rpc_server_instance, gui_dispatcher, worker_manager

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
    if port is None:
        try:
            port = int(settings.get("rpc_port", 9875))
        except (TypeError, ValueError):
            port = 9875
    configure_parts_library_path(FreeCAD.getUserAppDataDir())
    remote_enabled = settings.get("remote_enabled", False)
    allowed_ips = settings.get("allowed_ips", "127.0.0.1")
    version = tuple(str(part) for part in FreeCAD.Version()[:4])
    while len(version) < 4:
        version += ("",)
    worker_manager = WorkerManager(
        WorkerRuntime(
            gui_executable=sys.executable,
            freecad_home=FreeCAD.getHomePath(),
            gui_version=version,
            configured_path=settings.get("freecadcmd_path", ""),
        ),
        os.path.dirname(__file__),
    )

    if remote_enabled:
        host = "0.0.0.0"
    else:
        host = "localhost"

    rpc_server_instance = FilteredXMLRPCServer(
        (host, port), allowed_ips_str=allowed_ips, allow_none=True, logRequests=False
    )
    rpc_server_instance.register_instance(
        FreeCADRPC(
            allow_execute_code=(
                not remote_enabled
                or bool(settings.get("allow_remote_execute_code", False))
            )
        )
    )

    def server_loop():
        logger.info("RPC Server started at %s:%s", host, port)
        if remote_enabled:
            logger.info("Remote connections enabled. Allowed IPs: %s", allowed_ips)
        rpc_server_instance.serve_forever()

    rpc_server_thread = threading.Thread(target=server_loop, daemon=True)
    rpc_server_thread.start()

    msg = f"RPC Server started at {host}:{port}."
    if remote_enabled:
        msg += f" Allowed IPs: {allowed_ips}"
    return msg


def stop_rpc_server():
    global rpc_server_instance, rpc_server_thread, gui_dispatcher, worker_manager

    if rpc_server_instance:
        server = rpc_server_instance
        thread = rpc_server_thread
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
        if dispatcher is not None:
            dispatcher.deleteLater()
        logger.info("RPC Server stopped")
        if completed.is_set():
            return "RPC Server stopped."
        return "RPC Server shutdown is continuing in the background."

    return "RPC Server was not running."


class StartRPCServerCommand:
    def GetResources(self):
        return {"MenuText": "Start RPC Server", "ToolTip": "Start RPC Server"}

    def Activated(self):
        msg = start_rpc_server()
        FreeCAD.Console.PrintMessage(msg + "\n")

    def IsActive(self):
        return True


class StopRPCServerCommand:
    def GetResources(self):
        return {"MenuText": "Stop RPC Server", "ToolTip": "Stop RPC Server"}

    def Activated(self):
        msg = stop_rpc_server()
        FreeCAD.Console.PrintMessage(msg + "\n")

    def IsActive(self):
        return True


class ToggleRemoteConnectionsCommand:
    def GetResources(self):
        return {
            "MenuText": "Remote Connections",
            "ToolTip": "Enable or disable remote connections for the RPC server.",
            "Checkable": True,
        }

    def Activated(self, checked=0):
        settings = load_settings()
        settings["remote_enabled"] = bool(checked)
        save_settings(settings)

        if settings["remote_enabled"]:
            allowed_ips = settings.get("allowed_ips", "127.0.0.1")
            FreeCAD.Console.PrintMessage(
                f"Remote connections enabled. Allowed IPs: {allowed_ips}\n"
            )
        else:
            FreeCAD.Console.PrintMessage("Remote connections disabled.\n")

        if rpc_server_instance:
            FreeCAD.Console.PrintMessage(
                "Restart the RPC server for changes to take effect.\n"
            )

    def IsActive(self):
        return True


class ConfigureAllowedIPsCommand:
    def GetResources(self):
        return {
            "MenuText": "Configure Allowed IPs",
            "ToolTip": "Set which IP addresses or subnets are allowed to connect to the RPC server.",
        }

    def Activated(self):
        settings = load_settings()
        current_ips = settings.get("allowed_ips", "127.0.0.1")
        text, ok = QtWidgets.QInputDialog.getText(
            None,
            "Allowed IP Addresses",
            "Enter allowed IP addresses or subnets (comma-separated):\n"
            "Examples: 127.0.0.1, 192.168.1.0/24, 10.0.0.5",
            QtWidgets.QLineEdit.Normal,
            current_ips,
        )
        if ok and text.strip():
            valid, errors = validate_allowed_ips(text.strip())
            if errors:
                QtWidgets.QMessageBox.warning(
                    None,
                    "Invalid IP Configuration",
                    "The following errors were found:\n\n"
                    + "\n".join(f"• {e}" for e in errors)
                    + ("\n\nOnly valid entries will be saved."
                       if valid else "\n\nNo valid entries found. Settings not changed."),
                )
            if not valid:
                FreeCAD.Console.PrintWarning("Allowed IPs not changed — no valid entries.\n")
                return
            normalised = ", ".join(valid)
            settings["allowed_ips"] = normalised
            save_settings(settings)
            FreeCAD.Console.PrintMessage(
                f"Allowed IPs updated to: {normalised}\n"
            )
            if rpc_server_instance:
                FreeCAD.Console.PrintMessage(
                    "Restart the RPC server for changes to take effect.\n"
                )
        else:
            FreeCAD.Console.PrintMessage("Allowed IPs not changed.\n")

    def IsActive(self):
        return True


class ToggleAutoStartCommand:
    def GetResources(self):
        return {
            "MenuText": "Auto-Start Server",
            "ToolTip": "Automatically start the RPC server when FreeCAD launches.",
            "Checkable": True,
        }

    def Activated(self, checked=0):
        settings = load_settings()
        settings["auto_start_rpc"] = bool(checked)
        save_settings(settings)

        if settings["auto_start_rpc"]:
            FreeCAD.Console.PrintMessage(
                "MCP RPC server will start automatically on next FreeCAD launch.\n"
            )
        else:
            FreeCAD.Console.PrintMessage(
                "MCP RPC server auto-start disabled.\n"
            )

    def IsActive(self):
        return True


FreeCADGui.addCommand("Start_RPC_Server", StartRPCServerCommand())
FreeCADGui.addCommand("Stop_RPC_Server", StopRPCServerCommand())
FreeCADGui.addCommand("Toggle_Auto_Start", ToggleAutoStartCommand())
FreeCADGui.addCommand("Toggle_Remote_Connections", ToggleRemoteConnectionsCommand())
FreeCADGui.addCommand("Configure_Allowed_IPs", ConfigureAllowedIPsCommand())


def _sync_toggle_states():
    """Sync checkable menu items with saved settings on startup."""
    try:
        settings = load_settings()
        main_window = FreeCADGui.getMainWindow()
        toggle_map = {
            "Remote Connections": settings.get("remote_enabled", False),
            "Auto-Start Server": settings.get("auto_start_rpc", False),
        }
        found = 0
        for action in main_window.findChildren(QtWidgets.QAction):
            if action.text() in toggle_map:
                action.setChecked(toggle_map[action.text()])
                found += 1
                if found == len(toggle_map):
                    return
    except Exception:
        pass
    # Retry if menu not ready yet
    QtCore.QTimer.singleShot(2000, _sync_toggle_states)


QtCore.QTimer.singleShot(2000, _sync_toggle_states)
