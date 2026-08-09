"""Invoke GUI save phase for typed save."""
try: from ....dispatch.request_cancellation_error import RequestCancellationError  # noqa: E701, I001 - frozen census lines
except ImportError: from dispatch.request_cancellation_error import RequestCancellationError  # noqa: E701, I001 - frozen census lines
from .save_typed_helpers import make_error_response, marker_keys_for
from .save_typed_invoke_helpers import (
    assert_live_identity_unchanged,
    invoke_save_with_capability,
    record_invoke_save_error,
    revalidate_save_invocation,
)


def invoke_save_gui_phase(
    self,
    *,
    phase,
    inflight,
    captured_identity,
    request_id,
    mode,
    destination,
    collaborators,
):
    marker_keys = []
    attribution_started = False
    credential = phase["credential"]
    try:
        if inflight is not None:
            inflight.token.checkpoint("save_gui_revalidation")
        document = collaborators.freecad.getDocument(phase["document_name"])
        if document is None:
            raise RuntimeError("document closed before save invocation")
        original_identity = phase["original_identity"]
        marker_keys = marker_keys_for(document, original_identity, destination)
        dl = collaborators.import_document_lock()
        dl.begin_agent_mutation_scope(request_id, marker_keys)
        attribution_started = True
        lease = collaborators.import_document_lease()
        revalidate_save_invocation(credential, phase, lease, collaborators)
        assert_live_identity_unchanged(
            document, original_identity, phase, lease, collaborators
        )
        if inflight is not None:
            inflight.token.begin_mutation("save_invocation")
        phase["invocation"] = invoke_save_with_capability(
            self, document, phase, mode, collaborators
        )
        if inflight is not None:
            inflight.token.checkpoint("save_invocation_complete")
        return {"success": True}
    except RequestCancellationError:
        self._complete_request_cancellation(
            inflight,
            dirty=(
                True
                if inflight is not None and inflight.token.snapshot().mutation_started
                else None
            ),
        )
        raise
    except Exception as exc:
        from contextlib import suppress

        with suppress(Exception):
            record_invoke_save_error(
                exc,
                credential=credential,
                phase=phase,
                captured_identity=captured_identity,
                request_id=request_id,
                inflight=inflight,
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
