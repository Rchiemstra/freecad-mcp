"""Finalize inflight cancellation after a cancel_request admission."""

from __future__ import annotations

from ...telemetry import emit as emit_telemetry
from .control_cancel_handoff import handoff_public


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
    lease_events = []
    if target is not None and cancellation.status != "completed":
        target.token.set_phase("cancellation_requested")
        lease_events = self._begin_request_cancellation(target)
        emit_telemetry(
            "cancellation",
            "cancellation_acknowledged",
            status="warning",
            request_id=target_request_id,
            execution_id=target_request_id,
            payload={"lease_event_count": len(lease_events or ())},
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
        lease_events = self._complete_request_cancellation(target)
    elif target is not None and cancellation.status in {"already_requested", "completed"}:
        cached = target.token.cancellation_resolution()
        if cached is not None:
            lease_events = cached
    mcp_runtime_id = collaborators.import_document_lock().get_request_identity().get(
        "instance_id"
    )
    return {
        "success": True,
        "target_request_id": target_request_id,
        "cancellation": cancellation.to_public_dict(),
        "gui_queue": queue_status,
        "lease_events": lease_events,
        "handoff_cancelled": False,
        "handoff_continuation": handoff_public(
            collaborators.handoff_continuation_store,
            mcp_runtime_id,
            target_request_id,
        ),
    }
