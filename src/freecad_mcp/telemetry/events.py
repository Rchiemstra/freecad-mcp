"""Versioned telemetry event construction and validation constants."""

from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any, Mapping

from ..build_info import event_schema_version
from .context import get_context


EVENT_NAMES = frozenset(
    {
        "authentication_completed",
        "authentication_failed",
        "authentication_started",
        "cancellation_acknowledged",
        "cancellation_completed",
        "cancellation_requested",
        "deprecation_observed",
        "document_health_checked",
        "gui_execution_completed",
        "gui_execution_late_completed",
        "gui_execution_queued",
        "gui_execution_started",
        "gui_execution_timeout",
        "policy_rejected",
        "recovery_completed",
        "recovery_failed",
        "recovery_started",
        "routing_completed",
        "rpc_invocation_completed",
        "rpc_invocation_failed",
        "rpc_invocation_started",
        "session_started",
        "session_stopped",
        "tool_call_completed",
        "tool_call_received",
        "transaction_aborted",
        "transaction_committed",
        "transaction_rollback_failed",
        "transaction_started",
        "validation_completed",
        "validation_started",
        "worker_job_cancel_requested",
        "worker_job_cancelled",
        "worker_job_completed",
        "worker_job_created",
        "worker_job_started",
        "worker_job_timeout",
    }
)


def utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def build_event(
    *,
    sequence: int,
    source: str,
    event: str,
    status: str,
    duration_ms: float | None = None,
    error_code: str | None = None,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    context = get_context()
    return {
        "schema_version": event_schema_version,
        "timestamp": utc_timestamp(),
        "monotonic_ns": time.monotonic_ns(),
        "sequence": int(sequence),
        "source": str(source),
        "event": str(event),
        "status": str(status),
        "session_id": context.session_id,
        "task_id": context.task_id or None,
        "call_id": context.call_id or None,
        "attempt_number": context.attempt_number,
        "parent_call_id": context.parent_call_id or None,
        "request_id": context.request_id or None,
        "execution_id": context.execution_id or None,
        "worker_job_id": context.worker_job_id or None,
        "document_session_uuid": context.document_session_uuid or None,
        "recovery_incident_id": context.recovery_incident_id or None,
        "duration_ms": (
            None if duration_ms is None else round(float(duration_ms), 3)
        ),
        "error_code": None if error_code is None else str(error_code),
        "payload": dict(payload or {}),
    }


__all__ = ["EVENT_NAMES", "build_event", "utc_timestamp"]
