"""Request-status state resolution helpers."""

from __future__ import annotations


def inflight_state(inflight, status):
    if status.status == "expired":
        return "expired"
    if inflight is None:
        return _status_without_inflight(status)
    if inflight.terminal:
        return _terminal_inflight_state(inflight, status)
    if inflight.cancellation_requested:
        return "cancel_requested"
    if inflight.uncertain:
        return "running_after_timeout"
    if inflight.active_gui_phases:
        return "running"
    return "queued"


def _status_without_inflight(status):
    if status.status == "completed":
        return "completed"
    if status.status in {"new", "in_progress"}:
        return "running"
    return "unknown"


def _terminal_inflight_state(inflight, status):
    if inflight.cancellation_requested:
        if (
            status.response
            and isinstance(status.response, dict)
            and status.response.get("late_completion")
        ):
            return "completed_after_cancel_request"
        return "cancelled"
    if inflight.terminal_status == "failed":
        return "failed"
    return "completed"
