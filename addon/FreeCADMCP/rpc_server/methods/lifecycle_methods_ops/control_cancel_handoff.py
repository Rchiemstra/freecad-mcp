"""Handoff continuation helpers for request cancellation."""

from __future__ import annotations

from ...telemetry import emit as emit_telemetry


def handoff_public(store, mcp_runtime_id, target_request_id):
    if store is None or not mcp_runtime_id:
        return None
    entry = store.get(mcp_runtime_id, target_request_id)
    return entry.to_public_dict() if entry is not None else None


def handoff_entry(store, mcp_runtime_id, target_request_id, cached_entry=None):
    if cached_entry is not None:
        return cached_entry
    if store is None or not mcp_runtime_id:
        return None
    return store.get(mcp_runtime_id, target_request_id)


def request_handoff_cancel(store, mcp_runtime_id, target_request_id):
    if store is None or not mcp_runtime_id or not target_request_id:
        return None, None
    handoff_entry_value = store.get(mcp_runtime_id, target_request_id)
    handoff_cancel_status = store.request_cancel(mcp_runtime_id, target_request_id)
    if handoff_entry_value is None and handoff_cancel_status != "not_found":
        handoff_entry_value = store.get(mcp_runtime_id, target_request_id)
    return handoff_cancel_status, handoff_entry_value


def not_cancellable_message(state):
    if state == "claimable":
        return (
            "LOCKED_ERROR handoff already escrowed a claimable credential; "
            "call claim_acquisition_result instead of cancelling"
        )
    if state == "claim_committed":
        return (
            "LOCKED_ERROR handoff has crossed the ownership-rotation "
            "boundary; continue polling get_request_status because an "
            "escrowed credential may not exist yet"
        )
    return (
        "LOCKED_ERROR handoff has crossed an irreversible boundary "
        "and cannot be cancelled"
    )


def handoff_block_response(
    *,
    target_request_id,
    error_code,
    error,
    cancellation_status,
    handoff_store,
    mcp_runtime_id,
    cached_entry=None,
):
    return {
        "success": False,
        "error_code": error_code,
        "error": error,
        "target_request_id": target_request_id,
        "cancellation": {"status": cancellation_status, "cancel_requested": False},
        "gui_queue": "not_queued",
        "lease_events": [],
        "handoff_cancelled": False,
        "handoff_continuation": handoff_public(
            handoff_store, mcp_runtime_id, target_request_id
        ),
    }


def handoff_cancelled_response(
    handoff_store, target_request_id, mcp_runtime_id
):
    emit_telemetry(
        "cancellation",
        "cancellation_requested",
        status="warning",
        request_id=target_request_id,
        execution_id=target_request_id,
        payload={"registry_status": "handoff_continuation"},
    )
    return {
        "success": True,
        "target_request_id": target_request_id,
        "cancellation": {"status": "handoff_cancelled", "cancel_requested": True},
        "gui_queue": "not_queued",
        "lease_events": [],
        "handoff_cancelled": True,
        "handoff_continuation": handoff_public(
            handoff_store, mcp_runtime_id, target_request_id
        ),
    }


def handoff_completed_tombstone_response(
    handoff_store, target_request_id, mcp_runtime_id
):
    emit_telemetry(
        "cancellation",
        "cancellation_requested",
        status="warning",
        request_id=target_request_id,
        execution_id=target_request_id,
        payload={"registry_status": "completed_tombstone_handoff"},
    )
    return {
        "success": True,
        "target_request_id": target_request_id,
        "cancellation": {"status": "handoff_cancelled", "cancel_requested": True},
        "gui_queue": "not_queued",
        "lease_events": [],
        "handoff_cancelled": True,
        "handoff_continuation": handoff_public(
            handoff_store, mcp_runtime_id, target_request_id
        ),
    }


def resolve_handoff_block(
    handoff_store,
    handoff_cancel_status,
    *,
    target_request_id,
    mcp_runtime_id,
    handoff_entry_value,
):
    if handoff_cancel_status == "not_cancellable":
        entry = handoff_entry(
            handoff_store, mcp_runtime_id, target_request_id, handoff_entry_value
        )
        state = entry.state if entry is not None else "claim_committed"
        return handoff_block_response(
            target_request_id=target_request_id,
            error_code="REQUEST_NOT_CANCELLABLE",
            error=not_cancellable_message(state),
            cancellation_status="not_cancellable",
            handoff_store=handoff_store,
            mcp_runtime_id=mcp_runtime_id,
            cached_entry=handoff_entry_value,
        )
    if handoff_cancel_status == "terminal_failed":
        entry = handoff_entry(
            handoff_store, mcp_runtime_id, target_request_id, handoff_entry_value
        )
        return handoff_block_response(
            target_request_id=target_request_id,
            error_code=(entry.error_code if entry is not None else None)
            or "LOCKED_ERROR_HANDOFF_FAILED",
            error=(entry.error if entry is not None else None)
            or "LOCKED_ERROR handoff failed; no credential is available to claim",
            cancellation_status="terminal_failed",
            handoff_store=handoff_store,
            mcp_runtime_id=mcp_runtime_id,
            cached_entry=handoff_entry_value,
        )
    if handoff_cancel_status == "terminal_denied":
        entry = handoff_entry(
            handoff_store, mcp_runtime_id, target_request_id, handoff_entry_value
        )
        return handoff_block_response(
            target_request_id=target_request_id,
            error_code=(entry.error_code if entry is not None else None)
            or "LOCKED_ERROR_HANDOFF_DENIED",
            error=(entry.error if entry is not None else None)
            or "LOCKED_ERROR handoff was denied; no credential is available to claim",
            cancellation_status="terminal_denied",
            handoff_store=handoff_store,
            mcp_runtime_id=mcp_runtime_id,
            cached_entry=handoff_entry_value,
        )
    if handoff_cancel_status == "already_claimed":
        return handoff_block_response(
            target_request_id=target_request_id,
            error_code="REQUEST_ALREADY_COMPLETED",
            error=(
                "LOCKED_ERROR handoff credential is already in custody; "
                "cancellation is impossible and no token is returned"
            ),
            cancellation_status="already_completed",
            handoff_store=handoff_store,
            mcp_runtime_id=mcp_runtime_id,
            cached_entry=handoff_entry_value,
        )
    return None
