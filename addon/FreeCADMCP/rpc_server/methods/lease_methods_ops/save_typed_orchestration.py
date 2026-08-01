"""Typed save orchestration helpers."""

from ...inflight_requests import RequestCancellationError
from ._common import _rpc_mod
from .save_typed_errors import (
    record_preflight_save_error,
    record_validation_save_error,
)
from .save_typed_helpers import make_error_response


def run_save_preflight(
    self,
    *,
    mode,
    phase,
    destination,
    overwrite,
    expected_destination_sha256,
    validation_profile,
    inflight,
):
    try:
        self._request_checkpoint("save_filesystem_preflight")
        if mode == "save":
            preflight = _rpc_mod().save_service.prepare_save(
                phase["source_path"],
                expected_baseline=phase["lease_baseline"],
                expected_path=phase["original_identity"].canonical_path,
                validation_profile=validation_profile,
            )
        else:
            preflight = _rpc_mod().save_service.prepare_save_as(
                phase["source_path"],
                destination,
                source_baseline=phase["lease_baseline"],
                overwrite=bool(overwrite),
                expected_destination_sha256=(expected_destination_sha256 or None),
                validation_profile=validation_profile,
            )
        phase["preflight"] = preflight
        self._request_checkpoint("save_filesystem_preflight_complete")
        return None
    except RequestCancellationError:
        self._complete_request_cancellation(inflight)
        raise
    except Exception as exc:
        return exc


def run_save_verification(
    self,
    *,
    invocation,
    phase,
    inflight,
    validate_in_worker,
):
    try:
        self._request_checkpoint("save_reopen_verification")
        result = _rpc_mod().save_service.verify_saved_file(
            invocation, domain_validator=validate_in_worker
        )
        self._request_checkpoint("save_reopen_verification_complete")
        return result
    except RequestCancellationError:
        self._complete_request_cancellation(inflight, dirty=True)
        raise
    except Exception as exc:
        return exc


def handle_preflight_failure(
    self,
    failure,
    *,
    phase,
    captured_identity,
    request_id,
    inflight,
    mode,
):
    def preflight_error_gui():
        record_preflight_save_error(
            failure,
            phase=phase,
            captured_identity=captured_identity,
            request_id=request_id,
            inflight=inflight,
        )
        return True

    self._dispatch_gui(preflight_error_gui, timeout=self.EXECUTE_TIMEOUT)
    return make_error_response(
        self, failure, mode=mode, request_id=request_id, phase=phase
    )


def run_save_invocation(
    self,
    *,
    phase,
    inflight,
    captured_identity,
    request_id,
    mode,
    destination,
    invoke_save_gui_phase_impl,
):
    def invoke_save_gui_phase():
        return invoke_save_gui_phase_impl(
            self,
            phase=phase,
            inflight=inflight,
            captured_identity=captured_identity,
            request_id=request_id,
            mode=mode,
            destination=destination,
        )

    self._request_checkpoint("save_invocation_queue")
    invoked = self._dispatch_gui(invoke_save_gui_phase, timeout=self.EXECUTE_TIMEOUT)
    if not isinstance(invoked, dict) or not invoked.get("success"):
        return invoked
    invocation = phase.get("invocation")
    if invocation is None:
        return {
            "success": False,
            "error_code": "SAVE_PHASE_RESULT_MISSING",
            "error": "GUI save completed without an invocation record",
        }
    return invocation


def handle_validation_failure(
    self,
    failure,
    *,
    phase,
    captured_identity,
    request_id,
    inflight,
    mode,
):
    def validation_error_gui():
        record_validation_save_error(
            failure,
            phase=phase,
            captured_identity=captured_identity,
            request_id=request_id,
            inflight=inflight,
        )
        return True

    self._dispatch_gui(validation_error_gui, timeout=self.EXECUTE_TIMEOUT)
    return make_error_response(
        self, failure, mode=mode, request_id=request_id, phase=phase
    )
