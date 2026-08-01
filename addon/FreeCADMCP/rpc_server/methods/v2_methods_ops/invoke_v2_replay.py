"""Replay-cache short-circuit handling for invoke_v2."""

from __future__ import annotations

from typing import Any


def refresh_acquisition_replay_error(
    cached: dict[str, Any],
    *,
    session,
    envelope,
    claim_store: Any,
) -> dict[str, Any]:
    """Attach claimable status to a non-replayable acquisition error."""
    refreshed = dict(cached)
    error = dict(cached["error"])
    error["claimable"] = claim_store.claimable(
        session.mcp.runtime_id, envelope.request_id
    )
    refreshed["error"] = error
    return refreshed


def completed_replay_response(
    *,
    replay,
    envelope,
    session,
    invocation_runtime_id: str,
    claim_store: Any,
) -> dict[str, Any]:
    """Build the outbound payload for a completed replay claim."""
    if (
        claim_store is not None
        and envelope.method
        in {
            "acquire_document_lock",
            "adopt_dirty_document",
            "create_document",
        }
    ):
        claimed = claim_store.claim(session.mcp.runtime_id, envelope.request_id)
        if claimed is not None:
            return {
                "ok": True,
                "request_id": envelope.request_id,
                "addon_runtime_id": invocation_runtime_id,
                "result": claimed,
                "claimed_acquisition_result": True,
            }
    cached = replay.response
    if (
        isinstance(cached, dict)
        and isinstance(cached.get("error"), dict)
        and cached["error"].get("code") == "ACQUISITION_RESULT_NOT_REPLAYABLE"
        and claim_store is not None
    ):
        return refresh_acquisition_replay_error(
            cached,
            session=session,
            envelope=envelope,
            claim_store=claim_store,
        )
    return cached


def in_progress_replay_response(*, envelope, invocation_runtime_id: str) -> dict[str, Any]:
    """Build the outbound payload for an in-progress replay claim."""
    return {
        "ok": False,
        "request_id": envelope.request_id,
        "addon_runtime_id": invocation_runtime_id,
        "error": {
            "code": "REQUEST_IN_PROGRESS",
            "message": "The matching authenticated request is still running",
        },
    }
