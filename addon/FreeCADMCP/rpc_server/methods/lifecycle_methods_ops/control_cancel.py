"""Authentication-scoped request cancellation."""

from __future__ import annotations

from .control_cancel_finalize import finalize_cancel_request


def cancel_request(self, target_request_id):
    """Cancel one request owned by this authenticated RPC session."""

    collaborators = self._execution_collaborators
    identity = collaborators.request_identity_provider().get_request_identity()
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
    if cancellation.status == "unknown":
        return {
            "success": False,
            "error_code": "REQUEST_NOT_FOUND",
            "error": "No cancellable request exists in this authenticated session",
        }
    if cancellation.status == "not_cancellable":
        return {
            "success": False,
            "error_code": "REQUEST_NOT_CANCELLABLE",
            "error": "The request has crossed an irreversible completion boundary",
            "target_request_id": target_request_id,
            "cancellation": cancellation.to_public_dict(),
        }
    target = collaborators.inflight_request_registry.get(
        session_id, target_request_id
    )
    return finalize_cancel_request(
        self,
        session_id=session_id,
        target_request_id=target_request_id,
        cancellation=cancellation,
        target=target,
        collaborators=collaborators,
    )
