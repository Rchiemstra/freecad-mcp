"""Lease RPC methods extracted from ``FreeCADRPC`` (Phase 4 slice 4E)."""

from ._common import _rpc_mod
from .save_legacy_orchestration import (
    run_legacy_invoke_phase,
    run_legacy_prepare_phase,
    run_legacy_promote_phase,
    verify_legacy_save,
    verify_legacy_saved_file,
)


def run_legacy_save(self, selector, *, validation_profile="default"):
    """Run a verified same-path save for a proven live v1 observe lease."""

    dl = _rpc_mod()._import_document_lock()
    if dl.is_enforcement_enabled():
        return {
            "success": False,
            "error_code": "LEASE_PROTOCOL_REQUIRED",
            "error": "Protocol-v1 save compatibility is disabled in enforce mode",
        }
    if _rpc_mod().save_service is None:
        return {
            "success": False,
            "error_code": "SAVE_SERVICE_UNAVAILABLE",
            "error": "The typed save service is not initialized",
        }

    captured_identity = dict(dl.get_request_identity())
    token = str(captured_identity.get("lease_token") or "")
    phase = {}
    inflight = self._current_inflight()

    prepared = run_legacy_prepare_phase(
        self,
        selector=selector,
        captured_identity=captured_identity,
        request_id=str(captured_identity.get("request_id") or ""),
        phase=phase,
        dl=dl,
        validation_profile=validation_profile,
        token=token,
        inflight=inflight,
    )
    if not isinstance(prepared, dict) or not prepared.get("success"):
        return prepared

    preflight = verify_legacy_save(
        self, phase, validation_profile, captured_identity, inflight, dl, token
    )
    if isinstance(preflight, dict):
        return preflight

    invoked = run_legacy_invoke_phase(
        self,
        phase=phase,
        dl=dl,
        captured_identity=captured_identity,
        request_id=str(captured_identity.get("request_id") or ""),
        preflight=preflight,
        inflight=inflight,
    )
    if not isinstance(invoked, dict) or not invoked.get("success"):
        return invoked

    result = verify_legacy_saved_file(
        self, phase, captured_identity, inflight, dl, token
    )
    if isinstance(result, dict):
        return result

    return run_legacy_promote_phase(
        self,
        phase=phase,
        dl=dl,
        token=token,
        result=result,
        captured_identity=captured_identity,
        inflight=inflight,
    )
