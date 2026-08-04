from __future__ import annotations

from .control_cancel_finalize import finalize_cancel_request
from .control_cancel_handoff import (
    handoff_cancelled_response,
    handoff_completed_tombstone_response,
    handoff_public,
    request_handoff_cancel,
    resolve_handoff_block,
)


def cancel_request(self, target_request_id):
    """Cancel one request owned by this authenticated RPC session.

    This is a reserved control-plane operation.  It is intentionally not
    registered as a FastMCP/model-facing tool.

    For async LOCKED_ERROR handoff, the continuation state overrides an
    inflight tombstone: irreversible/claimable states always return
    ``REQUEST_NOT_CANCELLABLE``, while terminal failed/denied return their
    actual details (never claim advice).
    """
    collaborators = self._execution_collaborators
    identity = collaborators.import_document_lock().get_request_identity()
    session_id = identity.get("authenticated_session_id")
    if not session_id:
        return {
            "success": False,
            "error_code": "AUTHENTICATED_SESSION_REQUIRED",
            "error": "Request cancellation is scoped to an authenticated session",
        }
    target_request_id = str(target_request_id or "")
    cancellation = collaborators.inflight_request_registry.request_cancel(
        session_id, target_request_id
    )
    mcp_runtime_id = identity.get("instance_id")
    handoff_cancel_status, handoff_entry = request_handoff_cancel(
        collaborators.handoff_continuation_store,
        mcp_runtime_id,
        target_request_id,
    )
    blocked = resolve_handoff_block(
        collaborators.handoff_continuation_store,
        handoff_cancel_status,
        target_request_id=target_request_id,
        mcp_runtime_id=mcp_runtime_id,
        handoff_entry_value=handoff_entry,
    )
    if blocked is not None:
        return blocked

    handoff_cancelled = handoff_cancel_status in {"cancelled", "already_cancelled"}
    if cancellation.status == "unknown":
        if handoff_cancelled:
            return handoff_cancelled_response(
                collaborators.handoff_continuation_store,
                target_request_id,
                mcp_runtime_id,
            )
        return {
            "success": False,
            "error_code": "REQUEST_NOT_FOUND",
            "error": "No cancellable request exists in this authenticated session",
        }
    if handoff_cancelled and cancellation.status == "completed":
        return handoff_completed_tombstone_response(
            collaborators.handoff_continuation_store,
            target_request_id,
            mcp_runtime_id,
        )
    if cancellation.status == "not_cancellable":
        return {
            "success": False,
            "error_code": "REQUEST_NOT_CANCELLABLE",
            "error": "The request has crossed an irreversible completion boundary",
            "target_request_id": target_request_id,
            "cancellation": cancellation.to_public_dict(),
            "handoff_cancelled": handoff_cancelled,
            "handoff_continuation": handoff_public(
                collaborators.handoff_continuation_store,
                mcp_runtime_id,
                target_request_id,
            ),
        }
    target = collaborators.inflight_request_registry.get(
        session_id, target_request_id
    )
    response = finalize_cancel_request(
        self,
        session_id=session_id,
        target_request_id=target_request_id,
        cancellation=cancellation,
        target=target,
        collaborators=collaborators,
    )
    response["handoff_cancelled"] = handoff_cancelled
    return response
