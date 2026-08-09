"""Typed save error-recovery GUI helpers."""

from ...save_service import SaveServiceError

try:
    from document_state import document_modified_or_dirty
except ImportError:  # pragma: no cover - flat addon import path
    from addon.FreeCADMCP.document_state import document_modified_or_dirty


def record_preflight_save_error(
    failure,
    *,
    phase,
    captured_identity,
    request_id,
    inflight,
    collaborators,
):
    credential = phase["credential"]
    try:
        if (
            isinstance(failure, SaveServiceError)
            and failure.stage == "destination_preflight"
        ):
            collaborators.document_lease_service.cancel_save_before_mutation(
                credential
            )
            return
        document = collaborators.freecad.getDocument(phase["document_name"])
        collaborators.document_lease_service.record_error(
            credential,
            code=getattr(failure, "code", type(failure).__name__.upper()),
            message=collaborators.redact_rpc_diagnostic(
                failure,
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


def record_validation_save_error(
    failure,
    *,
    phase,
    captured_identity,
    request_id,
    inflight,
    collaborators,
):
    try:
        credential = phase["credential"]
        document = collaborators.freecad.getDocument(phase["document_name"])
        collaborators.document_lease_service.record_error(
            credential,
            code=getattr(failure, "code", type(failure).__name__.upper()),
            message=collaborators.redact_rpc_diagnostic(
                failure,
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
