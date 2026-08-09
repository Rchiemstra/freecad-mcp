"""Release GUI task for document lock release."""

from typing import Any

from .lifecycle_dependencies import LifecycleCollaborators


def release_document_gui(
    self,
    *,
    selector,
    disposition,
    captured_identity,
    inflight,
    collaborators: LifecycleCollaborators,
) -> dict[str, Any]:
    if inflight is not None:
        inflight.token.checkpoint("release_gui_revalidation")
    if disposition not in {"saved", "restored"}:
        raise ValueError(
            "Agents may release only a verified saved or restored document"
        )
    credential, document_identity, document = collaborators.credential_for_selector(
        selector, captured_identity
    )
    lease = collaborators.import_document_lease()
    record = collaborators.document_lease_service.authorize(
        credential,
        selector={"document_session_uuid": (document_identity.session_uuid)},
        allowed_states={lease.LeaseState.LOCKED_IDLE},
    )
    self._touch_inflight_credential(credential, inflight)
    evidence = collaborators.live_validation_evidence(
        document, document_identity, record
    )
    if inflight is not None:
        inflight.token.begin_irreversible("release_sidecar_cas")
    terminal = collaborators.document_lease_service.release_clean(
        credential, validation=evidence
    )
    try:
        collaborators.import_core_authority().sync_clear_from_release(document)
    except Exception:
        collaborators.freecad.Console.PrintWarning(
            "[MCP] core mutation owner clear failed after release\n"
        )
    collaborators.discard_terminal_snapshot(terminal)
    return {"success": True, "lease": terminal}
