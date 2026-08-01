"""Acquisition claim helpers."""

from ...handoff_continuations import HandoffContinuationStore
from ._common import _rpc_mod


def claim_handoff_continuation(mcp_runtime_id, request_id, continuation):
    if continuation.state in HandoffContinuationStore.ACTIVE:
        return {
            "success": False,
            "pending": True,
            "error_code": "ACQUISITION_CLAIM_PENDING",
            "error": (
                "LOCKED_ERROR handoff has not finished escrow yet; "
                "continue polling get_request_status"
            ),
            "request_id": request_id,
            "handoff_continuation": continuation.to_public_dict(),
            "result_claimable": False,
        }
    if continuation.state == "cancelled":
        return {
            "success": False,
            "error_code": (
                continuation.error_code or "LOCKED_ERROR_HANDOFF_CANCELLED"
            ),
            "error": (
                continuation.error
                or "LOCKED_ERROR handoff was cancelled; nothing to claim"
            ),
            "request_id": request_id,
            "handoff_continuation": continuation.to_public_dict(),
        }
    if continuation.state in {"failed", "denied"}:
        return {
            "success": False,
            "error_code": (
                continuation.error_code or "LOCKED_ERROR_HANDOFF_FAILED"
            ),
            "error": (
                continuation.error
                or "LOCKED_ERROR handoff ended without a claimable credential"
            ),
            "request_id": request_id,
            "handoff_continuation": continuation.to_public_dict(),
            "recovery_required": bool(
                continuation.error_code
                in {
                    "ACQUISITION_CREDENTIAL_ESCROW_FAILED",
                    "ACQUISITION_CREDENTIAL_UNAVAILABLE",
                }
                or (continuation.error or "").find("recovery") >= 0
            ),
        }
    if continuation.state == "claimed":
        return {
            "success": True,
            "already_claimed": True,
            "credential_stored": True,
            "token_exported": False,
            "request_id": request_id,
            "error": (
                "Acquisition credential was already taken into custody; "
                "no private token is returned"
            ),
            "handoff_continuation": continuation.to_public_dict(),
        }
    if continuation.state != "claimable":
        return None
    if _rpc_mod().rpc_acquisition_claim_store is None:
        return {
            "success": False,
            "error_code": "ACQUISITION_CLAIM_UNAVAILABLE",
            "error": (
                "No claimable acquisition credential remains for this request"
            ),
            "request_id": request_id,
        }
    claimed = _rpc_mod().rpc_acquisition_claim_store.claim(
        mcp_runtime_id, request_id
    )
    if claimed is None:
        _rpc_mod().rpc_handoff_continuation_store.update(
            mcp_runtime_id,
            request_id,
            state="failed",
            stage="handoff_failed",
            error_code="ACQUISITION_CREDENTIAL_UNAVAILABLE",
            error=(
                "Escrowed acquisition credential expired or is missing; "
                "ownership may require recovery"
            ),
        )
        updated = _rpc_mod().rpc_handoff_continuation_store.get(
            mcp_runtime_id, request_id
        )
        return {
            "success": False,
            "error_code": "ACQUISITION_CREDENTIAL_UNAVAILABLE",
            "error": (
                "Escrowed acquisition credential expired or is missing; "
                "ownership may require recovery"
            ),
            "request_id": request_id,
            "recovery_required": True,
            "handoff_continuation": (
                updated.to_public_dict() if updated is not None else None
            ),
        }
    return {
        "success": True,
        "request_id": request_id,
        **claimed,
    }
