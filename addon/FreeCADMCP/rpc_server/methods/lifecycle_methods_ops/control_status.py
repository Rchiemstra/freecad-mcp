from __future__ import annotations

import os

import FreeCAD

from ...lease_runtime import (
    _boot_identity,
    _process_started_at,
    _profile_fingerprint,
)
from ...settings import load_settings
from ._common import _rpc_mod
from .control_status_state import continuation_flags, continuation_state, inflight_state

try:
    from ...._shared.protocol.public_error import (
        public_error as lease_protocol_public_error,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.public_error import public_error as lease_protocol_public_error

try:
    from build_info import addon_build_id, addon_version
except ImportError:
    from addon.FreeCADMCP.build_info import addon_build_id, addon_version


def get_request_status(self, request_id):
    identity = _rpc_mod()._import_document_lock().get_request_identity()
    session_id = identity.get("authenticated_session_id")
    mcp_runtime_id = identity.get("instance_id")
    if _rpc_mod().rpc_request_replay_cache is None or not session_id or not mcp_runtime_id:
        return {
            "success": False,
            "error_code": "AUTHENTICATED_SESSION_REQUIRED",
            "error": "Request status requires an authenticated MCP runtime",
        }
    try:
        status = _rpc_mod().rpc_request_replay_cache.status(mcp_runtime_id, request_id)
        inflight = _rpc_mod().rpc_inflight_request_registry.status(session_id, request_id)
        state = inflight_state(inflight, status)
        continuation = (
            _rpc_mod().rpc_handoff_continuation_store.get(mcp_runtime_id, request_id)
            if _rpc_mod().rpc_handoff_continuation_store is not None
            else None
        )
        confirmation_pending = False
        handoff_pending = False
        if continuation is not None:
            confirmation_pending, handoff_pending = continuation_flags(continuation)
            state = continuation_state(continuation, state)
        return {
            "success": True,
            "request_id": request_id,
            "state": state,
            "stage": (
                continuation.stage
                if continuation is not None
                else (inflight.phase if inflight is not None else None)
            ),
            "execution_started": bool(
                inflight is not None and inflight.active_gui_phases
            ),
            "mutation_started": bool(
                inflight is not None and inflight.mutation_started
            ),
            "cancellation_requested": bool(
                (inflight is not None and inflight.cancellation_requested)
                or (
                    continuation is not None
                    and continuation.cancel_requested.is_set()
                )
            ),
            "completion_uncertain": bool(inflight is not None and inflight.uncertain)
            or (
                continuation is not None
                and continuation.state == "claiming_uncertain"
            ),
            "late_completion_available": bool(
                status.response
                and isinstance(status.response, dict)
                and status.response.get("late_completion")
            ),
            "result_available": bool(status.response is not None),
            "result_claimable": bool(
                _rpc_mod().rpc_acquisition_claim_store is not None
                and _rpc_mod().rpc_acquisition_claim_store.claimable(
                    mcp_runtime_id, request_id
                )
            ),
            "confirmation_pending": confirmation_pending,
            "handoff_pending": handoff_pending,
            "acquisition_claim": (
                _rpc_mod().rpc_acquisition_claim_store.public_status(
                    mcp_runtime_id, request_id
                )
                if _rpc_mod().rpc_acquisition_claim_store is not None
                else {"claimable": False}
            ),
            "recovery_incident_id": (
                inflight.recovery_incident_id if inflight is not None else None
            ),
            "response": status.response,
            "inflight": (
                inflight.to_public_dict() if inflight is not None else None
            ),
            "handoff_continuation": (
                continuation.to_public_dict() if continuation is not None else None
            ),
        }
    except Exception as exc:
        return lease_protocol_public_error(exc, request_id=request_id)


def ping(self):
    return True


def get_instance_info(self):
    """Report this addon instance's identity (lightweight, no GUI dispatch).

    Lets a client confirm it reached the intended FreeCAD when several
    isolated instances listen on nearby ports. ``instance_id`` comes from the
    per-profile settings (empty on the default profile).
    """
    try:
        settings = load_settings()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    try:
        profile_path = FreeCAD.getUserAppDataDir()
    except Exception:
        profile_path = None
    try:
        freecad_version = list(_rpc_mod()._freecad_version_parts())
    except Exception:
        freecad_version = []
    profile_id = (
        settings.get("profile_instance_id") or settings.get("instance_id", "") or ""
    )
    endpoint = _rpc_mod().rpc_server_actual_endpoint or {
        "host": settings.get("rpc_bind_host", "127.0.0.1"),
        "port": settings.get("rpc_port", 9875),
    }
    return {
        "ok": True,
        "instance_id": profile_id,
        "profile_instance_id": profile_id,
        "addon_runtime_id": _rpc_mod().rpc_server_runtime_id,
        "pid": os.getpid(),
        "freecad_process_started_at": (
            _rpc_mod().rpc_runtime_manifest.freecad_process_started_at
            if _rpc_mod().rpc_runtime_manifest is not None
            else _process_started_at()
        ),
        "boot_id": (
            _rpc_mod().rpc_runtime_manifest.boot_id
            if _rpc_mod().rpc_runtime_manifest is not None
            else _boot_identity()
        ),
        "addon_loaded_at": _rpc_mod().addon_loaded_at,
        "rpc_started_at": _rpc_mod().rpc_server_started_at,
        "host": endpoint.get("host"),
        "port": endpoint.get("port"),
        "actual_endpoint": endpoint,
        "profile_path": profile_path,
        "protocol_versions": [1, 2],
        "protocol_version": 2 if _rpc_mod().rpc_session_manager is not None else 1,
        "protocol_features": (
            list(_rpc_mod().rpc_runtime_manifest.features)
            if _rpc_mod().rpc_runtime_manifest is not None
            else []
        ),
        "rpc_method_capabilities": {
            "sketch_attach": {"parameters": ["attachment_offset"]},
        },
        "addon_version": addon_version,
        "addon_build_id": addon_build_id,
        "freecad_version": freecad_version,
        "profile_path_fingerprint": _profile_fingerprint(),
        "document_lease_mode": settings.get("document_lease_mode", "off"),
    }


def check_rpc_sync(self, nonce):
    """Round-trip a nonce through the GUI queue to prove call correlation."""
    res = self._dispatch_gui(lambda: {"nonce": nonce})
    identity = _rpc_mod()._import_document_lock().get_request_identity()
    recovery = _rpc_mod().rpc_inflight_request_registry.latest_recovery_incident(
        identity.get("authenticated_session_id")
    )
    if not isinstance(res, dict) or res.get("nonce") != nonce:
        return {
            "success": False,
            "expected_nonce": nonce,
            "received": res,
            "recovery_incident_id": (
                recovery.recovery_incident_id if recovery is not None else None
            ),
        }
    return {
        "success": True,
        "nonce": nonce,
        "recovery_incident_id": (
            recovery.recovery_incident_id if recovery is not None else None
        ),
    }
