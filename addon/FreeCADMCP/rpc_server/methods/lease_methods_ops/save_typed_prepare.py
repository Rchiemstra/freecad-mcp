"""Prepare GUI phase for typed save."""
try: from ....dispatch.request_cancellation_error import RequestCancellationError  # noqa: E701, I001 - frozen census lines
except ImportError: from dispatch.request_cancellation_error import RequestCancellationError  # noqa: E701, I001 - frozen census lines
from .save_typed_helpers import make_error_response
from .save_typed_prepare_helpers import (
    authorize_save_prepare,
    begin_save_reservation,
    populate_prepare_phase,
    validate_save_references,
)


def prepare_gui_phase(
    self,
    *,
    selector,
    captured_identity,
    request_id,
    phase,
    inflight,
    mode,
    destination,
    validation_profile,
    collaborators,
):
    credential = None
    save_state_entered = False
    marker_keys = []
    attribution_started = False
    try:
        if inflight is not None:
            inflight.token.checkpoint("save_prepare_gui")
        credential, document_identity, document = collaborators.credential_for_selector(
            selector, captured_identity
        )
        marker_keys = populate_prepare_phase(
            phase,
            credential=credential,
            document_identity=document_identity,
            document=document,
            destination=destination,
            validation_profile=validation_profile,
            collaborators=collaborators,
        )
        dl = collaborators.import_document_lock()
        dl.begin_agent_mutation_scope(request_id, marker_keys)
        attribution_started = True
        record = authorize_save_prepare(
            self,
            credential=credential,
            document_identity=document_identity,
            document=document,
            inflight=inflight,
            collaborators=collaborators,
        )
        validate_save_references(document_identity, collaborators)
        begin_save_reservation(credential, mode, destination, phase, collaborators)
        save_state_entered = True
        phase["lease_baseline"] = record.baseline
        return {"success": True}
    except RequestCancellationError:
        self._complete_request_cancellation(inflight)
        raise
    except Exception as exc:
        if credential is not None and save_state_entered:
            try:
                collaborators.document_lease_service.cancel_save_before_mutation(
                    credential
                )
            except Exception as recovery_exc:
                return make_error_response(
                    self,
                    recovery_exc,
                    mode=mode,
                    request_id=request_id,
                    phase=phase,
                    collaborators=collaborators,
                )
        return make_error_response(
            self,
            exc,
            mode=mode,
            request_id=request_id,
            phase=phase,
            collaborators=collaborators,
        )
    finally:
        dl = collaborators.import_document_lock()
        if attribution_started:
            dl.end_agent_mutation_scope(request_id, marker_keys)
