"""Release GUI task for document lock release."""

from typing import Any

from ._common import _rpc_mod


def release_document_gui(
    self,
    *,
    selector,
    disposition,
    captured_identity,
    inflight,
) -> dict[str, Any]:
    if inflight is not None:
        inflight.token.checkpoint("release_gui_revalidation")
    if disposition not in {"saved", "restored"}:
        raise ValueError(
            "Agents may release only a verified saved or restored document"
        )
    credential, document_identity, document = _rpc_mod()._credential_for_selector(
        selector, captured_identity
    )
    lease = _rpc_mod()._import_document_lease()
    record = _rpc_mod().document_lease_service.authorize(
        credential,
        selector={"document_session_uuid": (document_identity.session_uuid)},
        allowed_states={lease.LeaseState.LOCKED_IDLE},
    )
    self._touch_inflight_credential(credential, inflight)
    evidence = _rpc_mod()._live_validation_evidence(
        document, document_identity, record
    )
    if inflight is not None:
        inflight.token.begin_irreversible("release_sidecar_cas")
    terminal = _rpc_mod().document_lease_service.release_clean(
        credential, validation=evidence
    )
    try:
        from document_lease import core_authority

        core_authority.sync_clear_from_release(document)
    except Exception:
        _rpc_mod().FreeCAD.Console.PrintWarning(
            "[MCP] core mutation owner clear failed after release\n"
        )
    _rpc_mod()._discard_terminal_snapshot(terminal)
    return {"success": True, "lease": terminal}
