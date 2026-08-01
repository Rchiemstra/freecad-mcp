"""Helpers for acquisition and LOCKED_ERROR handoff polling."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, Literal

_AUTH_FAILURE_TOKENS = frozenset(
    {
        "unauthorized",
        "auth",
        "forbidden",
        "not authenticated",
        "session",
    }
)
_AUTH_ERROR_TOKENS = frozenset({"fail", "error", "denied", "invalid", "expired"})
_TERMINAL_HANDOFF_STATES = frozenset({"failed", "cancelled", "expired", "unknown"})
_PENDING_HANDOFF_STATES = frozenset(
    {
        "queued",
        "running",
        "running_after_timeout",
        "cancel_requested",
    }
)


def is_permanent_auth_failure(exc: BaseException) -> bool:
    message = str(exc).lower()
    return any(token in message for token in _AUTH_FAILURE_TOKENS) and any(
        token in message for token in _AUTH_ERROR_TOKENS
    )


def handoff_claimable(last_status: Mapping[str, Any]) -> bool:
    return bool(
        last_status.get("result_claimable")
        or (
            isinstance(last_status.get("acquisition_claim"), Mapping)
            and last_status["acquisition_claim"].get("claimable")
        )
    )


def try_claim_handoff_result(conn, target: str, last_status: Mapping[str, Any]):
    state = str(last_status.get("state") or "")
    if not (
        handoff_claimable(last_status)
        or (state == "completed" and last_status.get("result_claimable"))
    ):
        return None
    claimed = conn.claim_acquisition_result(target)
    if (
        isinstance(claimed, Mapping)
        and claimed.get("success")
        and isinstance(claimed.get("credential"), Mapping)
        and claimed["credential"].get("token")
    ):
        return dict(claimed)
    return None


def handoff_terminal_result(
    last_status: Mapping[str, Any],
    target: str,
) -> dict[str, Any]:
    continuation = last_status.get("handoff_continuation") or {}
    return {
        "success": False,
        "error_code": str(
            continuation.get("error_code") or "LOCKED_ERROR_HANDOFF_FAILED"
        ),
        "error": str(
            continuation.get("error")
            or last_status.get("error")
            or "LOCKED_ERROR handoff did not complete"
        ),
        "request_id": target,
        "status": last_status,
        "confirmation_pending": False,
        "handoff_pending": False,
    }


def handoff_still_pending(last_status: Mapping[str, Any]) -> bool:
    state = str(last_status.get("state") or "")
    return bool(
        last_status.get("confirmation_pending")
        or last_status.get("handoff_pending")
        or state in _PENDING_HANDOFF_STATES
    )


def handoff_terminal_state(last_status: Mapping[str, Any]) -> bool:
    return str(last_status.get("state") or "") in _TERMINAL_HANDOFF_STATES


def disconnected_handoff_result(
    target: str,
    last_status: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "success": False,
        "error_code": "LOCKED_ERROR_HANDOFF_PENDING",
        "error": (
            "disconnected while automatic LOCKED_ERROR handoff "
            "was processing; resume with get_request_status / "
            "claim_acquisition_result"
        ),
        "request_id": target,
        "status": last_status,
        "confirmation_pending": False,
        "handoff_pending": True,
    }


def auth_failure_handoff_result(target: str, exc: BaseException) -> dict[str, Any]:
    return {
        "success": False,
        "error_code": "LOCKED_ERROR_HANDOFF_FAILED",
        "error": str(exc),
        "request_id": target,
        "confirmation_pending": False,
        "handoff_pending": False,
    }


def pending_handoff_result(
    target: str,
    last_status: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "success": False,
        "error_code": "LOCKED_ERROR_HANDOFF_PENDING",
        "error": (
            "Automatic LOCKED_ERROR handoff is still processing; continue "
            "polling get_request_status / claim_acquisition_result"
        ),
        "request_id": target,
        "status": last_status,
        "confirmation_pending": False,
        "handoff_pending": True,
    }


def poll_locked_error_handoff(
    conn,
    target: str,
    *,
    poll_interval_s: float,
    deadline: float | None,
) -> dict[str, Any]:
    last_status: dict[str, Any] | None = None
    while True:
        if getattr(conn, "_disconnected", False):
            return disconnected_handoff_result(target, last_status)
        if deadline is not None and time.monotonic() >= deadline:
            break
        try:
            last_status = conn.get_request_status(target)
        except Exception as exc:
            if is_permanent_auth_failure(exc):
                return auth_failure_handoff_result(target, exc)
            last_status = None
        if isinstance(last_status, Mapping) and last_status.get("success"):
            poll_result = process_handoff_status_poll(conn, target, last_status)
            if isinstance(poll_result, dict):
                return poll_result
            if poll_result == "break":
                break
        time.sleep(poll_interval_s)
    return pending_handoff_result(target, last_status)


def process_handoff_status_poll(
    conn,
    target: str,
    last_status: Mapping[str, Any],
) -> dict[str, Any] | Literal["break"] | None:
    claimed = try_claim_handoff_result(conn, target, last_status)
    if claimed is not None:
        return claimed
    if handoff_terminal_state(last_status):
        return handoff_terminal_result(last_status, target)
    if not handoff_still_pending(last_status):
        return "break"
    return None
