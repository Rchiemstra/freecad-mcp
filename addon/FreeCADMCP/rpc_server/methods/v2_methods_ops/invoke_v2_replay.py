"""Replay-cache short-circuit handling for invoke_v2."""

from __future__ import annotations

from typing import Any


def completed_replay_response(
    *,
    replay,
    envelope,
    session,
    invocation_runtime_id: str,
    claim_store: Any,
) -> dict[str, Any]:
    """Return the cached native RPC result for a completed replay claim."""
    del envelope, session, invocation_runtime_id, claim_store
    return replay.response


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
