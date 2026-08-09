"""Response finalization and acquisition escrow for invoke_v2 dispatch."""

from __future__ import annotations

from typing import Any


def finalize_invoke_v2_response(
    *,
    collaborators,
    self,
    session,
    envelope,
    inflight,
    invocation_runtime_id: str,
    replay_cache,
    outbound: dict[str, Any],
    cached: dict[str, Any],
    status: str,
    handler_state: dict[str, Any],
    process_pinned: bool = False,
) -> dict[str, Any]:
    """Close the cancellation gate before publishing replay state."""
    terminal_check = collaborators.inflight_request_registry.finish_handler(
        session.session_id,
        envelope.request_id,
        status=status,
    )
    if terminal_check is not None and terminal_check.cancellation_requested:
        process_pinned = bool(
            process_pinned
            or terminal_check.mutation_started
            or terminal_check.uncertain
        )
        resolution = (
            inflight.token.cancellation_resolution()
            if terminal_check.cancellation_resolved
            else self._complete_request_cancellation(
                inflight,
                dirty=(
                    True
                    if terminal_check.mutation_started or terminal_check.uncertain
                    else None
                ),
            )
        )
        cancellation_response = {
            "ok": False,
            "request_id": envelope.request_id,
            "addon_runtime_id": invocation_runtime_id,
            "result": {
                "success": False,
                "error_code": (
                    "REQUEST_CANCELLED_AFTER_MUTATION"
                    if terminal_check.mutation_started or terminal_check.uncertain
                    else "REQUEST_CANCELLED"
                ),
                "error": "Authenticated request was cancelled",
                "cancellation": terminal_check.to_public_dict(),
                "cancellation_resolution": resolution,
            },
        }
        outbound.clear()
        outbound.update(cancellation_response)
        cached = cancellation_response
        status = "cancelled"
        collaborators.inflight_request_registry.finish_handler(
            session.session_id,
            envelope.request_id,
            status=status,
        )
    replay_cache.complete(
        session.mcp.runtime_id,
        envelope,
        cached,
        process_pinned=process_pinned,
    )
    handler_state["status"] = status
    handler_state["finalized"] = True
    return outbound
