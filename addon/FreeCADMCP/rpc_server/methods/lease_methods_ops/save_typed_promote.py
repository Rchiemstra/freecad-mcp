"""Promotion GUI phase for typed save."""
try: from ....dispatch.request_cancellation_error import RequestCancellationError  # noqa: E701, I001 - frozen census lines
except ImportError: from dispatch.request_cancellation_error import RequestCancellationError  # noqa: E701, I001 - frozen census lines
try:
    from document_state import document_modified_or_dirty
except ImportError:  # pragma: no cover - flat addon import path
    from addon.FreeCADMCP.document_state import document_modified_or_dirty
from .save_typed_helpers import make_error_response, marker_keys_for
from .save_typed_promote_helpers import (
    assert_saved_path_matches,
    build_save_promotion_response,
    maybe_release_after_save,
    revalidate_save_promotion,
)


def promote_gui_phase(
    self,
    *,
    phase,
    inflight,
    captured_identity,
    request_id,
    mode,
    destination,
    validation_profile,
    release,
    result,
    collaborators,
):
    marker_keys = []
    attribution_started = False
    credential = phase["credential"]
    try:
        if inflight is not None:
            inflight.token.checkpoint("save_promotion_gui")
        document = collaborators.freecad.getDocument(phase["document_name"])
        if document is None:
            raise RuntimeError("saved document closed before lease promotion")
        original_identity = phase["original_identity"]
        marker_keys = marker_keys_for(document, original_identity, destination)
        dl = collaborators.import_document_lock()
        dl.begin_agent_mutation_scope(request_id, marker_keys)
        attribution_started = True
        lease = collaborators.import_document_lease()
        revalidate_save_promotion(credential, phase, lease, collaborators)
        assert_saved_path_matches(document, phase, result, lease, collaborators)
        collaborators.save_service.revalidate_saved_document_gui(document, result)
        if mode == "save_as":
            verified = collaborators.document_lease_service.commit_save_as(
                credential,
                destination=result.path,
                baseline=result.baseline,
            )
        else:
            verified = collaborators.document_lease_service.mark_save_verified(
                credential, baseline=result.baseline
            )
        response = build_save_promotion_response(
            self,
            credential=credential,
            result=result,
            phase=phase,
            mode=mode,
            validation_profile=validation_profile,
            collaborators=collaborators,
        )
        response["lease"] = verified.to_public_dict()
        if release:
            response = maybe_release_after_save(
                self,
                credential=credential,
                document=document,
                result=result,
                inflight=inflight,
                response=response,
                collaborators=collaborators,
            )
        return response
    except RequestCancellationError:
        self._complete_request_cancellation(inflight, dirty=True)
        raise
    except Exception as exc:
        try:
            document = collaborators.freecad.getDocument(phase["document_name"])
            collaborators.document_lease_service.record_error(
                credential,
                code=getattr(exc, "code", type(exc).__name__.upper()),
                message=collaborators.redact_rpc_diagnostic(
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
