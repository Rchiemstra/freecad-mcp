"""Credential escrow for LOCKED_ERROR handoff continuation."""

from ._common import logger
from .handoff_journal import journal_handoff_terminal


def escrow_locked_error_handoff_claim(
    self,
    *,
    mcp_runtime_id,
    request_id,
    claimed,
):
    """Store CAS grant in the claim vault and mark the continuation claimable.

    Must run immediately after successful ``claim_locked_error_handoff`` so a
    claim-phase waiter timeout cannot discard the rotated credential. Vault
    failure after ownership CAS is a recovery-required terminal failure:
    the token is never published and the continuation is not claimable.
    """

    collaborators = self._collaboration_collaborators
    if not isinstance(claimed, dict) or not claimed.get("success"):
        return False
    credential = claimed.get("credential") or {}
    if not credential.get("token"):
        return False
    if collaborators.acquisition_claim_store is None:
        if collaborators.handoff_continuation_store is not None:
            collaborators.handoff_continuation_store.update(
                mcp_runtime_id,
                request_id,
                state="failed",
                stage="handoff_failed",
                error_code="ACQUISITION_CREDENTIAL_ESCROW_FAILED",
                error=(
                    "Ownership rotated but the acquisition claim vault is "
                    "unavailable; recovery is required and no claimable "
                    "credential exists"
                ),
            )
        journal_handoff_terminal(
            self,
            mcp_runtime_id=mcp_runtime_id,
            request_id=request_id,
            response={
                "ok": False,
                "request_id": request_id,
                "addon_runtime_id": collaborators.rpc_server_runtime_id,
                "result": {
                    "success": False,
                    "error_code": "ACQUISITION_CREDENTIAL_ESCROW_FAILED",
                    "error": (
                        "Ownership rotated but the acquisition claim vault "
                        "is unavailable; recovery is required"
                    ),
                    "request_id": request_id,
                    "recovery_required": True,
                    "confirmation_pending": False,
                    "handoff_pending": False,
                },
            },
        )
        return False
    try:
        collaborators.acquisition_claim_store.store(
            mcp_runtime_id=mcp_runtime_id,
            request_id=request_id,
            method="adopt_dirty_document",
            credential=credential,
            result=claimed,
        )
    except Exception as exc:
        logger.exception(
            "Failed to escrow LOCKED_ERROR handoff credential for %s",
            request_id,
        )
        if collaborators.handoff_continuation_store is not None:
            collaborators.handoff_continuation_store.update(
                mcp_runtime_id,
                request_id,
                state="failed",
                stage="handoff_failed",
                error_code="ACQUISITION_CREDENTIAL_ESCROW_FAILED",
                error=(
                    "Ownership rotated but credential escrow failed; "
                    "recovery is required and no claimable credential exists: "
                    f"{collaborators.redact_rpc_diagnostic(exc)}"
                ),
            )
        journal_handoff_terminal(
            self,
            mcp_runtime_id=mcp_runtime_id,
            request_id=request_id,
            response={
                "ok": False,
                "request_id": request_id,
                "addon_runtime_id": collaborators.rpc_server_runtime_id,
                "result": {
                    "success": False,
                    "error_code": "ACQUISITION_CREDENTIAL_ESCROW_FAILED",
                    "error": (
                        "Ownership rotated but credential escrow failed; "
                        "recovery is required and no claimable credential exists"
                    ),
                    "request_id": request_id,
                    "recovery_required": True,
                    "confirmation_pending": False,
                    "handoff_pending": False,
                },
            },
        )
        return False
    journal_handoff_terminal(
        self,
        mcp_runtime_id=mcp_runtime_id,
        request_id=request_id,
        response={
            "ok": False,
            "request_id": request_id,
            "addon_runtime_id": collaborators.rpc_server_runtime_id,
            "error": {
                "code": "ACQUISITION_RESULT_NOT_REPLAYABLE",
                "message": (
                    "This acquisition request already completed; "
                    "its one-time credential cannot be returned from "
                    "the replay cache"
                ),
                "claimable": True,
            },
        },
    )
    if collaborators.handoff_continuation_store is not None:
        collaborators.handoff_continuation_store.update(
            mcp_runtime_id,
            request_id,
            state="claimable",
            stage="handoff_complete",
        )
    return True
