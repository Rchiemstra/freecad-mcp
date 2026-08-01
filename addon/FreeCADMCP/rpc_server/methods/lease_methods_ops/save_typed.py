"""Lease RPC methods extracted from ``FreeCADRPC`` (Phase 4 slice 4E)."""

from typing import Any

from ._common import _rpc_mod
from .save_typed_invoke import invoke_save_gui_phase as invoke_save_gui_phase_impl
from .save_typed_orchestration import (
    handle_preflight_failure,
    handle_validation_failure,
    run_save_invocation,
    run_save_preflight,
    run_save_verification,
)
from .save_typed_prepare import prepare_gui_phase as prepare_gui_phase_impl
from .save_typed_promote import promote_gui_phase as promote_gui_phase_impl


def run_typed_save(
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
    if _rpc_mod().document_lease_service is None or _rpc_mod().save_service is None:
        return {
            "success": False,
            "error_code": "LEASE_PROTOCOL_UNAVAILABLE",
            "error": "Typed save requires document lease v2",
        }
    captured_identity = dict(_rpc_mod()._import_document_lock().get_request_identity())
    request_id = captured_identity.get("request_id")
    phase: dict[str, Any] = {}
    inflight = self._current_inflight()
    self._request_checkpoint("save_lifecycle_start")

    def prepare_gui_phase():
        return prepare_gui_phase_impl(
            self,
            selector=selector,
            captured_identity=captured_identity,
            request_id=request_id,
            phase=phase,
            inflight=inflight,
            mode=mode,
            destination=destination,
            validation_profile=validation_profile,
        )

    self._request_checkpoint("save_prepare_queue")
    prepared = self._dispatch_gui(prepare_gui_phase, timeout=self.EXECUTE_TIMEOUT)
    if not isinstance(prepared, dict) or not prepared.get("success"):
        return prepared

    preflight_failure = run_save_preflight(
        self,
        mode=mode,
        phase=phase,
        destination=destination,
        overwrite=overwrite,
        expected_destination_sha256=expected_destination_sha256,
        validation_profile=validation_profile,
        inflight=inflight,
    )
    if preflight_failure is not None:
        return handle_preflight_failure(
            self,
            preflight_failure,
            phase=phase,
            captured_identity=captured_identity,
            request_id=request_id,
            inflight=inflight,
            mode=mode,
        )

    invocation_result = run_save_invocation(
        self,
        phase=phase,
        inflight=inflight,
        captured_identity=captured_identity,
        request_id=request_id,
        mode=mode,
        destination=destination,
        invoke_save_gui_phase_impl=invoke_save_gui_phase_impl,
    )
    if isinstance(invocation_result, dict):
        return invocation_result
    invocation = invocation_result

    def validate_in_worker(saved_path, profile):
        return _rpc_mod()._validate_saved_document_worker(
            saved_path,
            phase["document_name"],
            profile,
            phase["validation_expectations"],
        )

    verification_failure = run_save_verification(
        self,
        invocation=invocation,
        phase=phase,
        inflight=inflight,
        validate_in_worker=validate_in_worker,
    )
    if isinstance(verification_failure, Exception):
        return handle_validation_failure(
            self,
            verification_failure,
            phase=phase,
            captured_identity=captured_identity,
            request_id=request_id,
            inflight=inflight,
            mode=mode,
        )
    result = verification_failure

    def promote_gui_phase():
        return promote_gui_phase_impl(
            self,
            phase=phase,
            inflight=inflight,
            captured_identity=captured_identity,
            request_id=request_id,
            mode=mode,
            destination=destination,
            validation_profile=validation_profile,
            release=release,
            result=result,
        )

    self._request_checkpoint("save_promotion_queue")
    return self._dispatch_gui(promote_gui_phase, timeout=self.EXECUTE_TIMEOUT)
