"""Legacy save orchestration helpers."""

from .save_legacy_phases import (
    hash_legacy_baseline,
    legacy_invoke_gui,
    legacy_prepare_gui,
    legacy_promote_gui,
    legacy_save_failure_response,
)


def run_legacy_prepare_phase(
    self,
    *,
    selector,
    captured_identity,
    request_id,
    phase,
    dl,
    validation_profile,
    token,
    inflight,
    collaborators,
):
    def prepare_gui():
        try:
            return legacy_prepare_gui(
                self,
                selector=selector,
                captured_identity=captured_identity,
                request_id=request_id,
                phase=phase,
                dl=dl,
                validation_profile=validation_profile,
                token=token,
                inflight=inflight,
                collaborators=collaborators,
            )
        except Exception as exc:
            return legacy_save_failure_response(
                self,
                exc,
                phase=phase,
                dl=dl,
                token=token,
                request_id=request_id,
                captured_identity=captured_identity,
                inflight=inflight,
                collaborators=collaborators,
                dirty=False,
            )

    self._request_checkpoint("legacy_save_prepare_queue")
    return self._dispatch_gui(prepare_gui, timeout=self.EXECUTE_TIMEOUT)


def run_legacy_invoke_phase(
    self,
    *,
    phase,
    dl,
    captured_identity,
    request_id,
    preflight,
    inflight,
    collaborators,
):
    def invoke_gui():
        try:
            return legacy_invoke_gui(
                self,
                phase=phase,
                dl=dl,
                captured_identity=captured_identity,
                request_id=request_id,
                preflight=preflight,
                inflight=inflight,
                collaborators=collaborators,
            )
        except Exception as exc:
            return legacy_save_failure_response(
                self,
                exc,
                phase=phase,
                dl=dl,
                token=str(captured_identity.get("lease_token") or ""),
                request_id=request_id,
                captured_identity=captured_identity,
                inflight=inflight,
                collaborators=collaborators,
            )

    self._request_checkpoint("legacy_save_invocation_queue")
    return self._dispatch_gui(invoke_gui, timeout=self.EXECUTE_TIMEOUT)


def run_legacy_promote_phase(
    self, *, phase, dl, token, result, captured_identity, inflight, collaborators
):
    def promote_gui():
        try:
            return legacy_promote_gui(
                self,
                phase=phase,
                dl=dl,
                token=token,
                result=result,
                collaborators=collaborators,
            )
        except Exception as exc:
            return legacy_save_failure_response(
                self,
                exc,
                phase=phase,
                dl=dl,
                token=token,
                request_id=str(captured_identity.get("request_id") or ""),
                captured_identity=captured_identity,
                inflight=inflight,
                collaborators=collaborators,
            )

    self._request_checkpoint("legacy_save_promotion_queue")
    return self._dispatch_gui(promote_gui, timeout=self.EXECUTE_TIMEOUT)


def verify_legacy_save(
    self,
    phase,
    validation_profile,
    captured_identity,
    inflight,
    dl,
    token,
    collaborators,
):
    try:
        return hash_legacy_baseline(self, phase, validation_profile, collaborators)
    except Exception as exc:
        return legacy_save_failure_response(
            self,
            exc,
            phase=phase,
            dl=dl,
            token=token,
            request_id=str(captured_identity.get("request_id") or ""),
            captured_identity=captured_identity,
            inflight=inflight,
            dirty=False,
            collaborators=collaborators,
        )


def verify_legacy_saved_file(
    self, phase, captured_identity, inflight, dl, token, collaborators
):
    try:
        return collaborators.save_service.verify_saved_file(
            phase["invocation"],
            domain_validator=lambda saved_path, profile: (
                collaborators.validate_saved_document_worker(
                    saved_path,
                    phase["document_name"],
                    profile,
                    phase["validation_expectations"],
                )
            ),
        )
    except Exception as exc:
        return legacy_save_failure_response(
            self,
            exc,
            phase=phase,
            dl=dl,
            token=token,
            request_id=str(captured_identity.get("request_id") or ""),
            captured_identity=captured_identity,
            inflight=inflight,
            collaborators=collaborators,
        )
