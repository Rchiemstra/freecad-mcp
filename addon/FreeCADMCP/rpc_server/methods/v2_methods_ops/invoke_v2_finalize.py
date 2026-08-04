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
                "lease_resolution": resolution,
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


def apply_acquisition_escrow(
    *,
    collaborators,
    response: dict[str, Any],
    result: dict[str, Any],
    envelope,
    session,
    invocation_runtime_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Escrow acquisition credentials and shape replay-cache payloads."""
    cached_response = response
    escrowed = False
    try:
        if collaborators.acquisition_claim_store is not None:
            collaborators.acquisition_claim_store.store(
                mcp_runtime_id=session.mcp.runtime_id,
                request_id=envelope.request_id,
                method=envelope.method,
                credential=result["credential"],
                result=result,
            )
            escrowed = True
    except Exception:
        collaborators.logger.exception(
            "Failed to retain private acquisition claim for %s",
            envelope.request_id,
        )
    if not escrowed:
        scrubbed = dict(result)
        scrubbed.pop("credential", None)
        scrubbed["success"] = False
        scrubbed["error_code"] = "ACQUISITION_CREDENTIAL_ESCROW_FAILED"
        scrubbed["error"] = (
            "Document ownership changed but the acquisition "
            "credential could not be escrowed; recovery is "
            "required and the token was never published"
        )
        scrubbed["recovery_required"] = True
        scrubbed["credential_stored"] = False
        response = {
            "ok": False,
            "request_id": envelope.request_id,
            "addon_runtime_id": invocation_runtime_id,
            "result": scrubbed,
        }
        cached_response = response
    else:
        claimable = bool(
            collaborators.acquisition_claim_store is not None
            and collaborators.acquisition_claim_store.claimable(
                session.mcp.runtime_id, envelope.request_id
            )
        )
        cached_response = {
            "ok": False,
            "request_id": envelope.request_id,
            "addon_runtime_id": invocation_runtime_id,
            "error": {
                "code": "ACQUISITION_RESULT_NOT_REPLAYABLE",
                "message": (
                    "This acquisition request already completed; "
                    "its one-time credential cannot be returned from "
                    "the replay cache"
                ),
                "claimable": claimable,
            },
        }
    return response, cached_response
