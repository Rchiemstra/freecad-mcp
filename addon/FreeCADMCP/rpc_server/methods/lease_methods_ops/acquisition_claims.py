"""Lease RPC methods extracted from ``FreeCADRPC`` (Phase 4 slice 4E)."""

from ._common import _rpc_mod
from .acquisition_claims_helpers import claim_handoff_continuation


def claim_acquisition_result(self, request_id):
    """Return a lost acquire/adopt/create credential exactly once.

    Public status never includes the token. Only the authenticated MCP
    runtime that initiated the request may claim it. Handoff continuations
    are authoritative when present: running/terminal states are reported
    before the vault is consulted.
    """

    identity = _rpc_mod()._import_document_lock().get_request_identity()
    mcp_runtime_id = identity.get("instance_id")
    if not mcp_runtime_id:
        return {
            "success": False,
            "error_code": "AUTHENTICATED_SESSION_REQUIRED",
            "error": "Acquisition claim requires an authenticated MCP runtime",
        }
    request_id = str(request_id or "")
    continuation = (
        _rpc_mod().rpc_handoff_continuation_store.get(mcp_runtime_id, request_id)
        if _rpc_mod().rpc_handoff_continuation_store is not None
        else None
    )
    if continuation is not None:
        handoff_result = claim_handoff_continuation(
            mcp_runtime_id, request_id, continuation
        )
        if handoff_result is not None:
            return handoff_result
    if _rpc_mod().rpc_acquisition_claim_store is None:
        return {
            "success": False,
            "error_code": "AUTHENTICATED_SESSION_REQUIRED",
            "error": "Acquisition claim requires an authenticated MCP runtime",
        }
    claimed = _rpc_mod().rpc_acquisition_claim_store.claim(mcp_runtime_id, request_id)
    if claimed is None:
        return {
            "success": False,
            "error_code": "ACQUISITION_CLAIM_UNAVAILABLE",
            "error": (
                "No claimable acquisition credential remains for this request"
            ),
            "request_id": request_id,
            "acquisition_claim": _rpc_mod().rpc_acquisition_claim_store.public_status(
                mcp_runtime_id, request_id
            ),
        }
    return {
        "success": True,
        "request_id": request_id,
        **claimed,
    }


def acknowledge_acquisition_claim(self, request_id):
    """Scrub a durable acquisition claim after the client custodied it."""

    identity = _rpc_mod()._import_document_lock().get_request_identity()
    mcp_runtime_id = identity.get("instance_id")
    if _rpc_mod().rpc_acquisition_claim_store is None or not mcp_runtime_id:
        return {
            "success": False,
            "error_code": "AUTHENTICATED_SESSION_REQUIRED",
            "error": (
                "Acquisition claim acknowledgement requires an authenticated "
                "MCP runtime"
            ),
        }
    request_id = str(request_id or "")
    acknowledged = _rpc_mod().rpc_acquisition_claim_store.acknowledge(
        mcp_runtime_id, request_id
    )
    if (
        acknowledged
        and _rpc_mod().rpc_handoff_continuation_store is not None
    ):
        _rpc_mod().rpc_handoff_continuation_store.update(
            mcp_runtime_id,
            request_id,
            state="claimed",
            stage="handoff_complete",
        )
    return {
        "success": True,
        "request_id": request_id,
        "acknowledged": bool(acknowledged),
        "acquisition_claim": _rpc_mod().rpc_acquisition_claim_store.public_status(
            mcp_runtime_id, request_id
        ),
        "handoff_continuation": (
            _rpc_mod().rpc_handoff_continuation_store.get(
                mcp_runtime_id, request_id
            ).to_public_dict()
            if _rpc_mod().rpc_handoff_continuation_store is not None
            and _rpc_mod().rpc_handoff_continuation_store.get(mcp_runtime_id, request_id)
            is not None
            else None
        ),
    }
