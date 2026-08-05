from __future__ import annotations

import os

from .control_status_state import inflight_state

try:
    from build_info import addon_build_id, addon_version
except ImportError:
    from addon.FreeCADMCP.build_info import addon_build_id, addon_version


def get_request_status(self, request_id):
    collaborators = self._execution_collaborators
    identity = collaborators.request_identity_provider().get_request_identity()
    session_id = identity.get("authenticated_session_id")
    mcp_runtime_id = identity.get("instance_id")
    if (
        collaborators.request_replay_cache is None
        or not session_id
        or not mcp_runtime_id
    ):
        return {
            "success": False,
            "error_code": "AUTHENTICATED_SESSION_REQUIRED",
            "error": "Request status requires an authenticated MCP runtime",
        }
    try:
        status = collaborators.request_replay_cache.status(mcp_runtime_id, request_id)
        inflight = collaborators.inflight_request_registry.status(
            session_id, request_id
        )
        state = inflight_state(inflight, status)
        return {
            "success": True,
            "request_id": request_id,
            "state": state,
            "stage": (
                inflight.phase if inflight is not None else None
            ),
            "execution_started": bool(
                inflight is not None and inflight.active_gui_phases
            ),
            "mutation_started": bool(
                inflight is not None and inflight.mutation_started
            ),
            "cancellation_requested": bool(
                inflight is not None and inflight.cancellation_requested
            ),
            "completion_uncertain": bool(inflight is not None and inflight.uncertain),
            "late_completion_available": bool(
                status.response
                and isinstance(status.response, dict)
                and status.response.get("late_completion")
            ),
            "result_available": bool(status.response is not None),
            "result_claimable": False,
            "confirmation_pending": False,
            "handoff_pending": False,
            "acquisition_claim": {"claimable": False},
            "recovery_incident_id": (
                inflight.recovery_incident_id if inflight is not None else None
            ),
            "response": status.response,
            "inflight": (
                inflight.to_public_dict() if inflight is not None else None
            ),
            "handoff_continuation": None,
        }
    except Exception as exc:
        return collaborators.lease_protocol_public_error(
            exc, request_id=request_id
        )


def ping(self):
    return True


def get_instance_info(self):
    """Report this addon instance's identity (lightweight, no GUI dispatch).

    Lets a client confirm it reached the intended FreeCAD when several
    isolated instances listen on nearby ports. ``instance_id`` comes from the
    per-profile settings (empty on the default profile).
    """
    collaborators = self._execution_collaborators
    try:
        settings = collaborators.load_settings()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    try:
        profile_path = collaborators.freecad.getUserAppDataDir()
    except Exception:
        profile_path = None
    try:
        freecad_version = list(collaborators.freecad_version_parts())
    except Exception:
        freecad_version = []
    profile_id = (
        settings.get("profile_instance_id") or settings.get("instance_id", "") or ""
    )
    endpoint = collaborators.actual_endpoint or {
        "host": settings.get("rpc_bind_host", "127.0.0.1"),
        "port": settings.get("rpc_port", 9875),
    }
    return {
        "ok": True,
        "instance_id": profile_id,
        "profile_instance_id": profile_id,
        "addon_runtime_id": collaborators.runtime_id,
        "pid": os.getpid(),
        "freecad_process_started_at": (
            collaborators.runtime_manifest.freecad_process_started_at
            if collaborators.runtime_manifest is not None
            else collaborators.process_started_at
        ),
        "boot_id": (
            collaborators.runtime_manifest.boot_id
            if collaborators.runtime_manifest is not None
            else collaborators.boot_id
        ),
        "addon_loaded_at": collaborators.addon_loaded_at,
        "rpc_started_at": collaborators.server_started_at,
        "host": endpoint.get("host"),
        "port": endpoint.get("port"),
        "actual_endpoint": endpoint,
        "profile_path": profile_path,
        "protocol_versions": [1, 2],
        "protocol_version": 2 if collaborators.session_manager is not None else 1,
        "protocol_features": (
            list(collaborators.runtime_manifest.features)
            if collaborators.runtime_manifest is not None
            else []
        ),
        "rpc_method_capabilities": {
            "sketch_attach": {"parameters": ["attachment_offset"]},
        },
        "addon_version": addon_version,
        "addon_build_id": addon_build_id,
        "freecad_version": freecad_version,
        "profile_path_fingerprint": collaborators.profile_fingerprint,
        "document_lease_mode": settings.get("document_lease_mode", "off"),
    }


def check_rpc_sync(self, nonce):
    """Round-trip a nonce through the GUI queue to prove call correlation."""
    res = self._dispatch_gui(lambda: {"nonce": nonce})
    collaborators = self._execution_collaborators
    identity = collaborators.request_identity_provider().get_request_identity()
    recovery = collaborators.inflight_request_registry.latest_recovery_incident(
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
