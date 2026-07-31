#!/usr/bin/env python3
"""P8 live dirty-document stale-recovery smoke validation.

Drives the real MCP server stack against a running FreeCAD RPC listener.
Requires FreeCAD started via ``python start_freecad.py`` from the repo root
with ``document_lease_mode=enforce``.

Official evidence path (Pass):
  1. Acquire lease in enforce mode and make the document dirty.
  2. Primary: run a >90s GUI execute_code probe while the lease stays non-STALE
     (P2 long-running incident prevention).
  3. Secondary: pause MCP heartbeats to simulate a watchdog-race STALE transition.
  4. Automatic recovery on the next mutation, with credential continuity.

Usage (from tools/mcp/freecad-mcp):
    .venv-windows\\Scripts\\python.exe scripts/p8_live_dirty_smoke.py

Writes a token-free JSON report to stdout and exits 0 on pass, 1 on fail, 2 on blocker.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
import uuid
import zipfile
import xmlrpc.client
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mcp.shared.memory import create_connected_server_and_client_session

from freecad_mcp import server as mcp_server
from freecad_mcp.build_info import build_id
from freecad_mcp.lease_manager import STALE_RECOVERY_OUTCOME_RECOVERED
from freecad_mcp.rpc_auth import (
    PROTOCOL_VERSION,
    REQUIRED_PROTOCOL_FEATURES,
    InstanceManifest,
    make_mcp_runtime_identity,
)


DOC_NAME_PREFIX = "P8DirtySmoke"
AGENT_ID = "p8-live-validator"
STALE_WAIT_S = 95.0
LONG_PROBE_S = 100.0
MIN_PROBE_S = 90.0
REQUIRED_LEASE_MODE = "enforce"

_GUI_BLOCKER_CODES = frozenset(
    {
        "GUI_BUSY_AFTER_TIMEOUT",
        "GUI_COMPLETION_UNCERTAIN",
        "GUI_DISPATCH_FAILED",
        "GUI_TIMEOUT",
        "GUI_TIMEOUT_BEFORE_EXECUTION",
        "GUI_TIMEOUT_DURING_EXECUTION",
        "LEASE_PROTOCOL_REQUIRED",
    }
)


def _parse_tool_result(result: Any) -> dict[str, Any]:
    if getattr(result, "structuredContent", None):
        payload = result.structuredContent
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, dict):
                merged = dict(data)
                if payload.get("success") is False:
                    merged.setdefault("success", False)
                if payload.get("error_code"):
                    merged.setdefault("error_code", payload.get("error_code"))
                if payload.get("message") and "error" not in merged:
                    merged.setdefault("error", payload.get("message"))
                return merged
            return payload.get("data") or payload
    text = ""
    if getattr(result, "content", None):
        for block in result.content:
            text += getattr(block, "text", "") or ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "raw": text,
            "isError": getattr(result, "isError", False),
        }


def _tool_succeeded(payload: dict[str, Any]) -> bool:
    if payload.get("isError"):
        return False
    if payload.get("success") is True:
        return True
    if payload.get("success") is False:
        return False
    return not payload.get("error") and not payload.get("error_code")


def _error_code(payload: dict[str, Any]) -> str | None:
    code = payload.get("error_code")
    if code:
        return str(code)
    error = payload.get("error")
    if isinstance(error, dict):
        nested = error.get("error_code") or error.get("code")
        if nested:
            return str(nested)
    return None


def _error_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("error", "message", "raw"):
        value = payload.get(key)
        if isinstance(value, dict):
            for nested_key in ("error", "message", "error_code", "code"):
                nested = value.get(nested_key)
                if nested:
                    parts.append(str(nested))
        elif value:
            parts.append(str(value))
    return " ".join(parts)


def _is_gui_unresponsive(payload: dict[str, Any]) -> bool:
    code = _error_code(payload)
    if code:
        if code in _GUI_BLOCKER_CODES or code.startswith("GUI_TIMEOUT"):
            return True
    text = _error_text(payload).lower()
    return "freecad gui" in text and "timed out" in text


def _blocked(report: dict[str, Any], blocker: str, **extra: Any) -> dict[str, Any]:
    report["verdict"] = "blocked"
    report["blocker"] = blocker
    report.update(extra)
    return report


def _lease_state(lock_payload: dict[str, Any]) -> str | None:
    lease = lock_payload.get("lease") or {}
    nested = lease.get("lease") or {}
    return nested.get("state") or lease.get("state")


def _is_locked_state(state: str | None) -> bool:
    return bool(state and str(state).startswith("LOCKED_"))


def _document_dirty(lock_payload: dict[str, Any]) -> bool | None:
    lease = lock_payload.get("lease") or {}
    document_state = lease.get("document_state") or {}
    dirty = document_state.get("dirty")
    if isinstance(dirty, bool):
        return dirty
    return None


def _lease_identity(payload: dict[str, Any]) -> dict[str, Any]:
    credential = payload.get("credential") or {}
    lease = payload.get("lease") or {}
    nested = lease.get("lease") if isinstance(lease.get("lease"), dict) else lease
    record = payload.get("record") or lease.get("record") or {}
    if not isinstance(record, dict):
        record = {}
    record_lease = record.get("lease") if isinstance(record.get("lease"), dict) else {}
    return {
        "lease_id": (
            credential.get("lease_id")
            or nested.get("lease_id")
            or record.get("lease_id")
            or record_lease.get("lease_id")
        ),
        "generation": (
            credential.get("generation")
            or nested.get("generation")
            or record.get("generation")
            or record_lease.get("generation")
        ),
        "document_session_uuid": (
            credential.get("document_session_uuid")
            or nested.get("document_session_uuid")
            or record.get("document_session_uuid")
            or record_lease.get("document_session_uuid")
        ),
    }


def _fcstd_valid(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 32:
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            return "Document.xml" in archive.namelist()
    except zipfile.BadZipFile:
        return False


def _freecad_build_identity(value: Any) -> tuple[str, str]:
    parts = list(value) if isinstance(value, (list, tuple)) else [value]
    rendered = [str(part) for part in parts if part is not None]
    version = ".".join(rendered[:3]) or "unknown"
    revision = rendered[3] if len(rendered) > 3 and rendered[3] else "unknown"
    return version, revision


def _resolve_auth_secret_file(info: dict[str, Any]) -> Path | None:
    env_path = os.environ.get("FREECAD_MCP_AUTH_FILE", "").strip()
    if env_path:
        candidate = Path(env_path)
        if candidate.is_file():
            return candidate

    profile_path = info.get("profile_path")
    if profile_path:
        settings_path = Path(str(profile_path)) / "freecad_mcp_settings.json"
        if settings_path.is_file():
            try:
                settings = json.loads(settings_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                settings = {}
            auth_secret = str(settings.get("auth_secret_file") or "").strip()
            if auth_secret:
                candidate = Path(auth_secret)
                if candidate.is_file():
                    return candidate
        default_secret = Path(str(profile_path)) / "freecad_mcp_auth.secret"
        if default_secret.is_file():
            return default_secret
    return None


def _bootstrap_mcp_process_identity() -> None:
    mcp_identity = make_mcp_runtime_identity(client_build_id=build_id)
    mcp_server.state.mcp_instance_id = mcp_identity.runtime_id
    mcp_server.state.mcp_pid = mcp_identity.pid
    mcp_server.state.mcp_host = mcp_identity.hostname
    mcp_server.state.mcp_process_started_at = mcp_identity.process_started_at
    mcp_server.state.mcp_client_label = os.environ.get(
        "FREECAD_MCP_CLIENT", "p8-live-validator"
    )


def _configure_mcp_enforce_auth(
    info: dict[str, Any],
    *,
    auth_secret_file: Path,
    host: str,
    port: int,
    instance_id: str,
) -> dict[str, Any]:
    freecad_version, freecad_revision = _freecad_build_identity(
        info.get("freecad_version")
    )
    endpoint = info.get("actual_endpoint") or {"host": host, "port": port}
    features = tuple(info.get("protocol_features") or REQUIRED_PROTOCOL_FEATURES)
    manifest = InstanceManifest(
        rpc_host=str(endpoint.get("host") or host),
        rpc_port=int(endpoint.get("port") or port),
        profile_instance_id=str(info.get("profile_instance_id") or instance_id),
        profile_path=str(info.get("profile_path") or ""),
        auth_secret_file=str(auth_secret_file),
        expected_freecad_pid=int(info.get("pid")),
        expected_freecad_process_started_at=str(
            info.get("freecad_process_started_at") or info.get("addon_loaded_at") or ""
        ),
        expected_addon_runtime_id=str(info.get("addon_runtime_id") or ""),
        expected_boot_id=str(info.get("boot_id") or ""),
        expected_protocol_version=int(info.get("protocol_version") or PROTOCOL_VERSION),
        expected_protocol_features=features,
        expected_addon_version=str(info.get("addon_version") or "unknown"),
        expected_addon_build_id=str(info.get("addon_build_id") or "unknown"),
        expected_freecad_version=freecad_version,
        expected_freecad_revision=freecad_revision,
        expected_profile_path_fingerprint=str(info.get("profile_path_fingerprint") or ""),
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    mcp_server.state.instance_manifest = manifest
    mcp_server.state.auth_file = str(auth_secret_file)
    return {
        "profile_instance_id": manifest.profile_instance_id,
        "auth_secret_file": str(auth_secret_file),
        "protocol_version": manifest.expected_protocol_version,
    }


def _credential_from_manager(session_uuid: str) -> dict[str, Any]:
    credential = mcp_server.state.lease_manager.get(
        document_session_uuid=session_uuid
    )
    if credential is None:
        return {}
    return {
        "lease_id": credential.lease_id,
        "generation": credential.generation,
        "document_session_uuid": credential.document_session_uuid,
    }


def _credential_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    credential = payload.get("credential") or {}
    lease = payload.get("lease") or {}
    document = payload.get("document") or {}
    return {
        "lease_id": credential.get("lease_id") or lease.get("lease_id"),
        "document_session_uuid": (
            credential.get("document_session_uuid")
            or lease.get("document_session_uuid")
            or document.get("session_uuid")
        ),
        "generation": credential.get("generation") or lease.get("generation"),
    }


def _rpc_proxy(host: str, port: int) -> xmlrpc.client.ServerProxy:
    return xmlrpc.client.ServerProxy(f"http://{host}:{port}", allow_none=True)


def _close_document_if_open(proxy: xmlrpc.client.ServerProxy, name: str) -> None:
    # Unauthenticated execute_code is blocked in enforce mode; cleanup happens
    # inside the authenticated MCP session instead.
    try:
        if name in proxy.list_documents():
            return
    except Exception:
        pass


def _rpc_gui_sanity(
    proxy: xmlrpc.client.ServerProxy,
    *,
    lease_mode: str | None,
) -> tuple[bool, dict[str, Any]]:
    started = time.monotonic()
    try:
        result = proxy.execute_code("import FreeCAD\nprint(1)")
    except Exception as exc:
        return False, {
            "success": False,
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_s": round(time.monotonic() - started, 1),
        }
    if not isinstance(result, dict):
        result = {"success": False, "error": "non-dict execute_code response"}
    result = dict(result)
    result["elapsed_s"] = round(time.monotonic() - started, 1)
    if result.get("success"):
        return True, result
    if (
        lease_mode == REQUIRED_LEASE_MODE
        and _error_code(result) == "LEASE_PROTOCOL_REQUIRED"
        and result["elapsed_s"] < 5.0
    ):
        result["enforce_mode_protocol_gate"] = True
        return True, result
    return False, result


async def _call(session, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = await session.call_tool(tool, arguments)
    payload = _parse_tool_result(result)
    if getattr(result, "isError", False) and not payload.get("success"):
        payload.setdefault("isError", True)
    return payload


async def _wait_for_stale(
    session,
    session_uuid: str,
    doc_name: str,
    *,
    timeout_s: float,
) -> tuple[bool, dict[str, Any]]:
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = await _call(
            session,
            "get_document_lock",
            {
                "selector": {
                    "document_session_uuid": session_uuid,
                    "document_name": doc_name,
                }
            },
        )
        if _is_gui_unresponsive(last):
            return False, last
        state = _lease_state(last)
        if state == "STALE":
            return True, last
        await asyncio.sleep(2.0)
    return False, last


async def _pause_heartbeats(pause_s: float) -> None:
    """Secondary watchdog-race path: pause MCP heartbeats so STALE can be observed."""

    task = None
    for item in asyncio.all_tasks():
        if item.get_coro().__qualname__.endswith("_lease_heartbeat_loop"):
            task = item
            break
    if task is None:
        raise RuntimeError("lease heartbeat task not found in MCP server lifespan")

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await asyncio.sleep(pause_s)
    new_task = asyncio.create_task(mcp_server._lease_heartbeat_loop())
    # Keep reference so the task is not garbage-collected.
    asyncio.get_running_loop()._p8_heartbeat_task = new_task  # type: ignore[attr-defined]


async def run_smoke(
    *,
    host: str,
    port: int,
    instance_id: str | None,
    skip_long_probe: bool,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "doc_name": f"{DOC_NAME_PREFIX}_{uuid.uuid4().hex[:8]}",
        "doc_name_prefix": DOC_NAME_PREFIX,
        "rpc_endpoint": f"{host}:{port}",
        "instance_id": instance_id,
        "required_lease_mode": REQUIRED_LEASE_MODE,
        "steps": [],
        "evidence": {},
        "verdict": "fail",
    }

    if skip_long_probe:
        return _blocked(
            report,
            "--skip-long-probe cannot produce a valid P8 Pass",
        )

    proxy = _rpc_proxy(host, port)
    if not proxy.ping():
        return _blocked(report, "FreeCAD RPC ping failed")

    info = proxy.get_instance_info()
    lease_mode = info.get("document_lease_mode") if isinstance(info, dict) else None
    report["evidence"]["instance_info"] = {
        k: info.get(k)
        for k in (
            "ok",
            "profile_instance_id",
            "document_lease_mode",
            "pid",
            "host",
            "port",
            "addon_build_id",
        )
        if isinstance(info, dict)
    }
    if lease_mode != REQUIRED_LEASE_MODE:
        return _blocked(
            report,
            f"document_lease_mode must be {REQUIRED_LEASE_MODE!r} (got {lease_mode!r})",
            evidence_hint="Restart FreeCAD after setting enforce mode in freecad_mcp_settings.json",
        )

    gui_ok, gui_probe = _rpc_gui_sanity(proxy, lease_mode=lease_mode)
    report["evidence"]["rpc_gui_sanity"] = {
        "success": gui_ok,
        "elapsed_s": gui_probe.get("elapsed_s"),
        "error_code": _error_code(gui_probe),
    }
    if not gui_ok:
        if _is_gui_unresponsive(gui_probe):
            return _blocked(
                report,
                "FreeCAD GUI dispatch is unresponsive (raw RPC execute_code sanity failed)",
                rpc_gui_error_code=_error_code(gui_probe),
            )
        return _blocked(
            report,
            "raw RPC execute_code sanity failed before MCP session",
            rpc_gui_error_code=_error_code(gui_probe),
        )

    mcp_server.state.rpc_host = host
    mcp_server.state.rpc_port = port
    mcp_server.state.instance_id = instance_id or (
        info.get("profile_instance_id") if isinstance(info, dict) else None
    )

    if lease_mode == REQUIRED_LEASE_MODE:
        _bootstrap_mcp_process_identity()
        auth_secret_file = _resolve_auth_secret_file(info if isinstance(info, dict) else {})
        if auth_secret_file is None:
            return _blocked(
                report,
                "enforce mode requires a readable auth secret file for MCP handshake",
            )
        try:
            report["evidence"]["mcp_auth_setup"] = _configure_mcp_enforce_auth(
                info if isinstance(info, dict) else {},
                auth_secret_file=auth_secret_file,
                host=host,
                port=port,
                instance_id=str(mcp_server.state.instance_id or ""),
            )
        except Exception as exc:
            return _blocked(
                report,
                f"could not build enforce-mode MCP auth manifest: {type(exc).__name__}",
                auth_error=str(exc),
            )

    save_path = Path(tempfile.gettempdir()) / f"p8_dirty_smoke_{uuid.uuid4().hex[:8]}.FCStd"
    report["save_path"] = str(save_path)

    doc_name = str(report["doc_name"])

    _close_document_if_open(proxy, doc_name)

    async with create_connected_server_and_client_session(
        mcp_server.mcp,
        read_timeout_seconds=timedelta(
            seconds=max(LONG_PROBE_S + STALE_WAIT_S + 180, 420)
        ),
        raise_exceptions=True,
    ) as session:
        created = await _call(session, "create_document", {"name": doc_name})
        report["steps"].append({"create_document": _tool_succeeded(created)})
        if not _tool_succeeded(created):
            if _is_gui_unresponsive(created):
                return _blocked(
                    report,
                    "create_document blocked by GUI dispatch timeout",
                    error_code=_error_code(created),
                )
            report["failure"] = "create_document failed"
            return report

        credential = _credential_from_payload(created)
        session_uuid = credential.get("document_session_uuid")
        if created.get("credential_stored") and session_uuid:
            acquired = created
            report["steps"].append(
                {
                    "acquire_document_lock": True,
                    "lease_state": _lease_state(acquired),
                    "via": "create_document_auto_lease",
                }
            )
        else:
            acquired = await _call(
                session,
                "acquire_document_lock",
                {
                    "doc_name": doc_name,
                    "task_description": "P8 dirty stale-recovery smoke",
                    "agent_id": AGENT_ID,
                },
            )
            report["steps"].append(
                {
                    "acquire_document_lock": acquired.get("success"),
                    "lease_state": _lease_state(acquired),
                }
            )
            if not acquired.get("success"):
                if _is_gui_unresponsive(acquired):
                    return _blocked(
                        report,
                        "acquire_document_lock blocked by GUI dispatch timeout",
                        error_code=_error_code(acquired),
                    )
                report["failure"] = "acquire_document_lock failed"
                report["acquire_error"] = acquired.get("error_code") or acquired.get(
                    "error"
                )
                return report
            credential = _credential_from_payload(acquired)
            session_uuid = credential.get("document_session_uuid")

        if not session_uuid:
            report["failure"] = "missing document_session_uuid after acquire"
            return report

        baseline_identity = _credential_from_manager(session_uuid)
        if not any(baseline_identity.values()):
            baseline_identity = _credential_from_payload(acquired)
        report["evidence"]["credential_baseline"] = {
            k: baseline_identity.get(k)
            for k in ("lease_id", "generation", "document_session_uuid")
        }
        if not baseline_identity.get("lease_id") or not baseline_identity.get(
            "document_session_uuid"
        ):
            report["failure"] = (
                "missing lease_id or document_session_uuid in baseline credential"
            )
            return report

        edit1 = await _call(
            session,
            "create_object",
            {
                "doc_name": doc_name,
                "obj_type": "Part::Box",
                "obj_name": "P8Box",
                "obj_properties": {"Length": 10, "Width": 10, "Height": 10},
            },
        )
        report["steps"].append({"dirty_edit_create_box": _tool_succeeded(edit1)})
        if not _tool_succeeded(edit1):
            if _is_gui_unresponsive(edit1):
                return _blocked(
                    report,
                    "dirty edit blocked by GUI dispatch timeout",
                    error_code=_error_code(edit1),
                )
            report["failure"] = "dirty edit (create_object) failed"
            return report

        lock_dirty = await _call(
            session,
            "get_document_lock",
            {
                "selector": {
                    "document_session_uuid": session_uuid,
                    "document_name": doc_name,
                }
            },
        )
        dirty_observed = _document_dirty(lock_dirty)
        report["evidence"]["dirty_before_stale"] = {
            "lease_state": _lease_state(lock_dirty),
            "dirty": dirty_observed,
        }
        if dirty_observed is not True:
            report["failure"] = (
                "dirty document not observed after create_object "
                f"(dirty={dirty_observed!r})"
            )
            return report

        probe_code = (
            f"doc = FreeCAD.getDocument({doc_name!r})\n"
            f"time.sleep({LONG_PROBE_S:.1f})\n"
            f"print('probe_done')"
        )
        probe_started = time.monotonic()
        probe = await _call(
            session,
            "execute_code",
            {
                "code": probe_code,
                "document": doc_name,
                "affected_documents": [doc_name],
                "execution_mode": "gui",
            },
        )
        probe_duration = time.monotonic() - probe_started
        lock_after_probe = await _call(
            session,
            "get_document_lock",
            {
                "selector": {
                    "document_session_uuid": session_uuid,
                    "document_name": doc_name,
                }
            },
        )
        probe_state = _lease_state(lock_after_probe)
        report["steps"].append(
            {
                "long_probe_seconds": round(probe_duration, 1),
                "probe_success": _tool_succeeded(probe),
                "lease_state_after_probe": probe_state,
            }
        )
        report["evidence"]["primary_long_probe"] = {
            "probe_duration_s": round(probe_duration, 1),
            "min_required_s": MIN_PROBE_S,
            "probe_success": _tool_succeeded(probe),
            "lease_remained_locked": _is_locked_state(probe_state),
            "lease_remained_non_stale": probe_state != "STALE",
            "p2_prevention_expected": True,
        }
        if not _tool_succeeded(probe):
            report["evidence"]["primary_long_probe"]["error_code"] = _error_code(probe)
            report["evidence"]["primary_long_probe"]["error"] = _error_text(probe)
            if _is_gui_unresponsive(probe):
                return _blocked(
                    report,
                    "long GUI probe blocked by GUI dispatch timeout",
                    error_code=_error_code(probe),
                )
            report["failure"] = "long GUI probe failed"
            return report
        if probe_duration < MIN_PROBE_S:
            report["failure"] = (
                f"long probe completed in {probe_duration:.1f}s; "
                f"requires >{MIN_PROBE_S:.0f}s"
            )
            return report
        if probe_state == "STALE":
            report["failure"] = (
                "lease transitioned to STALE during long probe; "
                "P2 prevention evidence not met"
            )
            return report
        if not _is_locked_state(probe_state):
            report["failure"] = (
                f"lease was not LOCKED_* during long probe "
                f"(got {probe_state!r}); P2 prevention evidence not met"
            )
            return report

        await _pause_heartbeats(STALE_WAIT_S)
        became_stale, stale_status = await _wait_for_stale(
            session,
            session_uuid,
            doc_name,
            timeout_s=30.0,
        )
        report["steps"].append(
            {
                "heartbeat_paused_s": STALE_WAIT_S,
                "observed_stale": became_stale,
                "lease_state": _lease_state(stale_status),
            }
        )
        report["evidence"]["secondary_watchdog_race"] = {
            "state": _lease_state(stale_status),
            "via": "heartbeat_pause_watchdog_race",
            "note": "secondary STALE injection; primary evidence is long probe + auto recovery",
        }
        if _is_gui_unresponsive(stale_status):
            return _blocked(
                report,
                "get_document_lock blocked while waiting for STALE",
                error_code=_error_code(stale_status),
            )
        if not became_stale:
            report["failure"] = "lease did not transition to STALE after heartbeat pause"
            return report

        recovery_edit = await _call(
            session,
            "edit_object",
            {
                "doc_name": doc_name,
                "obj_name": "P8Box",
                "obj_properties": {"Length": 12},
            },
        )
        recovery_summary = mcp_server.stale_recovery.recovery_status_snapshot_for(
            (session_uuid,)
        )
        if not _tool_succeeded(recovery_edit) and recovery_summary.get("succeeded"):
            recovery_edit = await _call(
                session,
                "edit_object",
                {
                    "doc_name": doc_name,
                    "obj_name": "P8Box",
                    "obj_properties": {"Length": 12},
                },
            )
            recovery_summary = mcp_server.stale_recovery.recovery_status_snapshot_for(
                (session_uuid,)
            )
        lock_recovered = await _call(
            session,
            "get_document_lock",
            {
                "selector": {
                    "document_session_uuid": session_uuid,
                    "document_name": doc_name,
                }
            },
        )
        recovery_summary = mcp_server.stale_recovery.recovery_status_snapshot_for(
            (session_uuid,)
        )
        recovered_identity = _credential_from_manager(session_uuid)
        if not any(recovered_identity.values()):
            recovered_identity = _lease_identity(lock_recovered)
        if not any(recovered_identity.values()):
            recovered_identity = _credential_from_payload(recovery_edit)
        recovered_outcome_seen = bool(recovery_summary.get("succeeded")) or any(
            item.get("outcome") == STALE_RECOVERY_OUTCOME_RECOVERED
            for item in recovery_summary.get("sessions", [])
            if isinstance(item, dict)
        )
        report["steps"].append(
            {
                "post_stale_edit": _tool_succeeded(recovery_edit),
                "lease_state_after_recovery": _lease_state(lock_recovered),
            }
        )
        report["evidence"]["automatic_recovery"] = {
            "lease_state": _lease_state(lock_recovered),
            "stale_recovery_summary": recovery_summary,
            "recovered_outcome_seen": recovered_outcome_seen,
            "credential_after_recovery": {
                k: recovered_identity.get(k)
                for k in ("lease_id", "generation", "document_session_uuid")
            },
            "credential_continuity": {
                "lease_id_unchanged": (
                    recovered_identity.get("lease_id")
                    == baseline_identity.get("lease_id")
                ),
                "session_uuid_unchanged": (
                    recovered_identity.get("document_session_uuid")
                    == baseline_identity.get("document_session_uuid")
                ),
                "generation_unchanged_or_advanced": (
                    isinstance(baseline_identity.get("generation"), int)
                    and isinstance(recovered_identity.get("generation"), int)
                    and recovered_identity["generation"]
                    >= baseline_identity["generation"]
                ),
            },
        }

        if not _tool_succeeded(recovery_edit):
            if _is_gui_unresponsive(recovery_edit):
                return _blocked(
                    report,
                    "post-STALE recovery edit blocked by GUI dispatch timeout",
                    error_code=_error_code(recovery_edit),
                )
            report["failure"] = "post-STALE recovery edit failed"
            return report
        if not recovered_outcome_seen:
            report["failure"] = "stale recovery outcome 'recovered' not observed"
            return report
        if _lease_state(lock_recovered) != "LOCKED_IDLE":
            report["failure"] = (
                f"automatic recovery did not restore LOCKED_IDLE "
                f"(got {_lease_state(lock_recovered)!r})"
            )
            return report

        continuity = report["evidence"]["automatic_recovery"]["credential_continuity"]
        if baseline_identity.get("lease_id") is None:
            report["failure"] = "baseline lease_id missing for continuity check"
            return report
        if recovered_identity.get("lease_id") is None:
            report["failure"] = "recovered lease_id missing for continuity check"
            return report
        if baseline_identity.get("document_session_uuid") is None:
            report["failure"] = (
                "baseline document_session_uuid missing for continuity check"
            )
            return report
        if recovered_identity.get("document_session_uuid") is None:
            report["failure"] = (
                "recovered document_session_uuid missing for continuity check"
            )
            return report
        if not continuity["lease_id_unchanged"]:
            report["failure"] = "lease_id changed after automatic recovery"
            return report
        if not continuity["session_uuid_unchanged"]:
            report["failure"] = "document_session_uuid changed after automatic recovery"
            return report
        if not continuity["generation_unchanged_or_advanced"]:
            report["failure"] = (
                "lease generation regressed after automatic recovery "
                f"(baseline={baseline_identity.get('generation')!r}, "
                f"recovered={recovered_identity.get('generation')!r})"
            )
            return report

        cont = await _call(
            session,
            "edit_object",
            {
                "doc_name": doc_name,
                "obj_name": "P8Box",
                "obj_properties": {"Width": 14},
            },
        )
        report["steps"].append({"continue_edit_after_recovery": _tool_succeeded(cont)})
        if not _tool_succeeded(cont):
            if _is_gui_unresponsive(cont):
                return _blocked(
                    report,
                    "continue edit after recovery blocked by GUI dispatch timeout",
                    error_code=_error_code(cont),
                )
            report["failure"] = "continue edit after recovery failed"
            return report

        saved = await _call(
            session,
            "save_document_as",
            {
                "selector": {
                    "document_session_uuid": session_uuid,
                    "document_name": doc_name,
                },
                "destination": str(save_path),
                "overwrite": True,
            },
        )
        on_disk_ok = _fcstd_valid(save_path)
        report["steps"].append(
            {
                "save_document_as": saved.get("success"),
                "on_disk_valid": on_disk_ok,
            }
        )
        report["evidence"]["save"] = {
            "path": str(save_path),
            "success": saved.get("success"),
            "on_disk_valid": on_disk_ok,
            "size_bytes": save_path.stat().st_size if save_path.is_file() else 0,
        }

        if not saved.get("success") or not on_disk_ok:
            if _is_gui_unresponsive(saved):
                return _blocked(
                    report,
                    "save_document_as blocked by GUI dispatch timeout",
                    error_code=_error_code(saved),
                )
            report["failure"] = "save_document_as failed or FCStd invalid on disk"
            return report

        report["verdict"] = "pass"
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("FREECAD_MCP_RPC_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("FREECAD_MCP_PORT", "9875")))
    parser.add_argument(
        "--instance-id",
        default=os.environ.get(
            "FREECAD_MCP_INSTANCE_ID", "63728e1a-d2a8-4d12-87dd-9c31ed98249c"
        ),
    )
    parser.add_argument(
        "--skip-long-probe",
        action="store_true",
        help="Dev-only shortcut; always exits blocked and cannot produce Pass",
    )
    args = parser.parse_args()

    try:
        report = asyncio.run(
            run_smoke(
                host=args.host,
                port=args.port,
                instance_id=args.instance_id,
                skip_long_probe=args.skip_long_probe,
            )
        )
    except Exception as exc:
        blocker = f"{type(exc).__name__}: {exc}"
        if hasattr(exc, "exceptions"):
            nested = [
                f"{type(item).__name__}: {item}" for item in getattr(exc, "exceptions", ())
            ]
            if nested:
                blocker = f"{blocker}; nested=[{'; '.join(nested)}]"
        report = {
            "verdict": "blocked",
            "blocker": blocker,
        }

    print(json.dumps(report, indent=2, sort_keys=True))
    verdict = report.get("verdict", "fail")
    if verdict == "pass":
        return 0
    if verdict == "blocked":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
