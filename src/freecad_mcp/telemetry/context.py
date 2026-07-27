"""Context-variable propagation for MCP correlation identifiers."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, replace
import os
from typing import Any, Iterator
import uuid


_PROCESS_SESSION_ID = os.environ.get("FREECAD_MCP_TELEMETRY_SESSION_ID") or str(
    uuid.uuid4()
)


@dataclass(frozen=True, slots=True)
class TelemetryContext:
    session_id: str = _PROCESS_SESSION_ID
    task_id: str = ""
    call_id: str = ""
    attempt_number: int | None = None
    parent_call_id: str = ""
    request_id: str = ""
    execution_id: str = ""
    worker_job_id: str = ""
    document_session_uuid: str = ""
    recovery_incident_id: str = ""
    operation: str = ""
    execution_category: str = ""


_CURRENT: ContextVar[TelemetryContext] = ContextVar(
    "freecad_mcp_telemetry_context", default=TelemetryContext()
)


def get_context() -> TelemetryContext:
    return _CURRENT.get()


def _clean_updates(values: dict[str, Any]) -> dict[str, Any]:
    fields = TelemetryContext.__dataclass_fields__
    cleaned: dict[str, Any] = {}
    for key, value in values.items():
        if key not in fields or value is None:
            continue
        if key == "attempt_number":
            try:
                cleaned[key] = int(value)
            except (TypeError, ValueError):
                continue
        else:
            cleaned[key] = str(value)
    return cleaned


@contextmanager
def bind_context(**values: Any) -> Iterator[TelemetryContext]:
    updated = replace(get_context(), **_clean_updates(values))
    token = _CURRENT.set(updated)
    try:
        yield updated
    finally:
        _CURRENT.reset(token)


def update_context(**values: Any) -> TelemetryContext:
    updated = replace(get_context(), **_clean_updates(values))
    _CURRENT.set(updated)
    return updated


def correlation_dict(*, include_empty: bool = True) -> dict[str, Any]:
    value = asdict(get_context())
    value.pop("operation", None)
    value.pop("execution_category", None)
    if include_empty:
        return value
    return {
        key: item
        for key, item in value.items()
        if item not in ("", None)
    }


__all__ = [
    "TelemetryContext",
    "bind_context",
    "correlation_dict",
    "get_context",
    "update_context",
]
