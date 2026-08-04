"""Compatibility imports for canonical GUI submission helpers."""

try:
    from ...dispatch.gui_submit import (
        build_gui_request,
        cancel_pending_after_timeout,
        emit_gui_queued_telemetry,
        enqueue_gui_request,
        execute_on_gui_thread,
        execute_request,
        finalize_completed_request,
        forget_cancelled_request,
        handle_submit_timeout,
        quarantine_running_timeout,
        raise_submit_timeout_error,
        unwrap_outcome,
        wait_for_race_winner,
        wait_for_request_completion,
    )
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from dispatch.gui_submit import (
        build_gui_request,
        cancel_pending_after_timeout,
        emit_gui_queued_telemetry,
        enqueue_gui_request,
        execute_on_gui_thread,
        execute_request,
        finalize_completed_request,
        forget_cancelled_request,
        handle_submit_timeout,
        quarantine_running_timeout,
        raise_submit_timeout_error,
        unwrap_outcome,
        wait_for_race_winner,
        wait_for_request_completion,
    )

__all__ = [
    "build_gui_request",
    "cancel_pending_after_timeout",
    "emit_gui_queued_telemetry",
    "enqueue_gui_request",
    "execute_on_gui_thread",
    "execute_request",
    "finalize_completed_request",
    "forget_cancelled_request",
    "handle_submit_timeout",
    "quarantine_running_timeout",
    "raise_submit_timeout_error",
    "unwrap_outcome",
    "wait_for_race_winner",
    "wait_for_request_completion",
]
