"""Invoke-phase helpers for typed save."""

from ...save_service import SaveServiceError

try:
    from document_state import document_modified_or_dirty
except ImportError:  # pragma: no cover - flat addon import path
    from addon.FreeCADMCP.document_state import document_modified_or_dirty


def revalidate_save_invocation(credential, phase, lease, collaborators):
    record = collaborators.document_lease_service.authorize(
        credential,
        selector={"document_session_uuid": phase["document_session_uuid"]},
        allowed_states={lease.LeaseState.LOCKED_SAVING},
    )
    if (
        record.state_revision != phase["saving_state_revision"]
        or record.last_mutation_revision != phase["saving_mutation_revision"]
    ):
        raise lease.CoordinationError(
            "lease changed during filesystem save preflight"
        )
    return record


def assert_live_identity_unchanged(
    document, original_identity, phase, lease, collaborators
):
    live_identity = collaborators.document_identity_service.inspect_registered_document(
        phase["document_session_uuid"], document
    )
    if (
        live_identity.comparison_key != original_identity.comparison_key
        or live_identity.file_identity != original_identity.file_identity
    ):
        raise lease.CoordinationError(
            "live document identity changed before save invocation"
        )
    return live_identity


def invoke_save_with_capability(self, document, phase, mode, collaborators):
    try:
        collaboration_runtime = collaborators.import_core_authority()
        save_kinds = collaboration_runtime.kinds_for_rpc_method(
            "save_document_as" if mode == "save_as" else "save_document",
            "save",
        )
        capability_cm = collaboration_runtime.open_mutation_capability(
            document,
            generation=int(getattr(phase["credential"], "generation", 0) or 0),
            kinds=save_kinds,
        )
    except Exception:
        from contextlib import nullcontext

        capability_cm = nullcontext(None)
    with capability_cm:
        if mode == "save":
            return collaborators.save_service.invoke_save_gui(
                document, phase["preflight"]
            )
        return collaborators.save_service.invoke_save_as_gui(
            document, phase["preflight"]
        )


def record_invoke_save_error(
    exc,
    *,
    credential,
    phase,
    captured_identity,
    request_id,
    inflight,
    collaborators,
):
    if (
        isinstance(exc, SaveServiceError)
        and exc.code == "SAVE_AS_DESTINATION_CONFLICT"
        and not exc.mutation_may_have_occurred
    ):
        collaborators.document_lease_service.cancel_save_before_mutation(credential)
        return
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
