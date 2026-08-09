"""Finalize inflight cancellation after a cancel_request admission."""

from __future__ import annotations

from ...telemetry import emit as emit_telemetry


def finalize_cancel_request(
    self,
    *,
    session_id,
    target_request_id,
    cancellation,
    target,
    collaborators,
):
    emit_telemetry(
        "cancellation",
        "cancellation_requested",
        status="warning",
        request_id=target_request_id,
        execution_id=target_request_id,
        payload={"registry_status": cancellation.status},
    )
    cancellation_resolution = []
    if target is not None and cancellation.status != "completed":
        target.token.set_phase("cancellation_requested")
        cancellation_resolution = self._begin_request_cancellation(target)
        emit_telemetry(
            "cancellation",
            "cancellation_acknowledged",
            status="warning",
            request_id=target_request_id,
            execution_id=target_request_id,
            payload={"resolution_count": len(cancellation_resolution or ())},
        )
    queue_status = "not_queued"
    if target is not None and collaborators.gui_dispatcher is not None:
        queue_status = collaborators.gui_dispatcher.cancel_request(
            session_id, target_request_id
        )
    if target is not None and queue_status in {"cancelled_pending", "completed"}:
        target.token.set_phase(
            "cancelled_before_gui_execution"
            if queue_status == "cancelled_pending"
            else "cancelled_after_gui_phase"
        )
        cancellation_resolution = self._complete_request_cancellation(target)
    elif target is not None and cancellation.status in {"already_requested", "completed"}:
        cached = target.token.cancellation_resolution()
        if cached is not None:
            cancellation_resolution = cached
    return {
        "success": True,
        "target_request_id": target_request_id,
        "cancellation": cancellation.to_public_dict(),
        "gui_queue": queue_status,
        "cancellation_resolution": cancellation_resolution,
    }
