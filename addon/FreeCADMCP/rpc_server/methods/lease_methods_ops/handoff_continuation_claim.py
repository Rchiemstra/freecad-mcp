"""Claim phase for LOCKED_ERROR handoff continuation."""

from ._common import _rpc_mod, require_document_modified
from .handoff_escrow import escrow_locked_error_handoff_claim


def claim_handoff_gui(
    self,
    *,
    store,
    mcp_runtime_id,
    request_id,
    phase,
    task_description,
    lease,
):
    document = _rpc_mod().FreeCAD.getDocument(phase["document_name"])
    if document is None:
        raise RuntimeError("document closed while handoff authorization was pending")
    original_identity = phase["document_identity"]
    observed = _rpc_mod().document_identity_service.inspect_registered_document(
        original_identity.session_uuid, document
    )
    if (
        observed.comparison_key != original_identity.comparison_key
        or observed.file_identity != original_identity.file_identity
    ):
        raise lease.CoordinationError(
            "live document identity changed during handoff authorization"
        )
    document_dirty = require_document_modified(document)
    if not document_dirty:
        raise lease.DirtyAdoptionError(
            "the document became clean during handoff authorization"
        )
    # Atomic cancel-vs-CAS gate after revalidation: cancel either
    # wins here or becomes not-cancellable for ownership rotation.
    if store is not None and not store.begin_claim(mcp_runtime_id, request_id):
        return {
            "success": False,
            "error_code": "LOCKED_ERROR_HANDOFF_CANCELLED",
            "error": "LOCKED_ERROR handoff was cancelled before claim",
            "request_id": request_id,
        }
    grant = _rpc_mod().document_lease_service.claim_locked_error_handoff(
        phase["exact_selector"],
        phase["owner"],
        validation=lease.LiveDocumentValidation(
            document=observed,
            document_modified=document_dirty,
            baseline=phase["baseline"],
            baseline_validated=bool(original_identity.canonical_path),
        ),
        local_confirmation=True,
        task_summary=task_description,
    )
    try:
        from document_lease import core_authority

        core_authority.sync_owner_from_lease_record(document, grant.record)
    except Exception:
        _rpc_mod().FreeCAD.Console.PrintWarning(
            "[MCP] core mutation owner sync failed after LOCKED_ERROR handoff\n"
        )
    claimed = {
        "success": True,
        **grant.to_dict(),
        "expiry_policy": {
            "heartbeat_interval_seconds": 10,
            "sidecar_flush_interval_seconds": 30,
            "stale_after_seconds": 90,
        },
    }
    # Escrow immediately after irreversible CAS so a claim-phase
    # waiter timeout cannot discard the rotated credential.
    if not escrow_locked_error_handoff_claim(
        self,
        mcp_runtime_id=mcp_runtime_id,
        request_id=request_id,
        claimed=claimed,
    ):
        scrubbed = dict(claimed)
        scrubbed.pop("credential", None)
        scrubbed["success"] = False
        scrubbed["error_code"] = "ACQUISITION_CREDENTIAL_ESCROW_FAILED"
        scrubbed["error"] = (
            "Ownership rotated but credential escrow failed; "
            "recovery is required and no claimable credential exists"
        )
        scrubbed["recovery_required"] = True
        scrubbed["request_id"] = request_id
        return scrubbed
    return claimed


def claim_late_complete(
    self,
    outcome,
    *,
    store,
    mcp_runtime_id,
    request_id,
    fail,
):
    """Backup escrow / terminal journal if the waiter already left."""

    if outcome is None:
        return
    if getattr(outcome, "ok", False):
        value = getattr(outcome, "value", None)
        if (
            isinstance(value, dict)
            and value.get("success")
            and (
                _rpc_mod().rpc_acquisition_claim_store is None
                or not _rpc_mod().rpc_acquisition_claim_store.claimable(
                    mcp_runtime_id, request_id
                )
            )
        ):
            # claim_handoff_gui already escrows; keep as belt/suspenders
            # for callers that might return success without store.
            escrow_locked_error_handoff_claim(
                self,
                mcp_runtime_id=mcp_runtime_id,
                request_id=request_id,
                claimed=value,
            )
        return
    # Late failure: only journal denied/failed when vault is empty.
    if (
        _rpc_mod().rpc_acquisition_claim_store is not None
        and _rpc_mod().rpc_acquisition_claim_store.claimable(mcp_runtime_id, request_id)
    ):
        return
    error = getattr(outcome, "error", None) or "LOCKED_ERROR handoff claim failed"
    fail("LEASE_CONFLICT", str(error))
