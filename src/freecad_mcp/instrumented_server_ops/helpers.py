"""Shared helpers for instrumented FastMCP."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..telemetry.context import TelemetryContext


def meta_values(context: Any) -> dict[str, Any]:
    try:
        meta = context.request_context.meta
    except (AttributeError, ValueError):
        return {}
    if meta is None:
        return {}
    if isinstance(meta, Mapping):
        return dict(meta)
    dump = getattr(meta, "model_dump", None)
    values = dump(by_alias=True) if callable(dump) else {}
    extra = getattr(meta, "model_extra", None)
    if isinstance(extra, Mapping):
        values.update(extra)
    return values


def first(values: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if values.get(name) not in (None, ""):
            return values[name]
    return None


def execution_category(tool_name: str) -> str:
    if tool_name == "execute_code":
        return "public_execute_code"
    if tool_name == "execute_code_async":
        return "deprecated_execute_code_async"
    if tool_name in {
        "get_worker_status",
        "cancel_worker_job",
        "compute_gear_geometry",
        "common_volume_along_path",
    }:
        return "read_only_worker_analysis"
    return "typed_direct_rpc"


def worker_context_updates(
    parent: TelemetryContext, worker: TelemetryContext
) -> dict[str, Any]:
    """Return telemetry fields the worker thread updated via update_context."""

    updates: dict[str, Any] = {}
    for field in TelemetryContext.__dataclass_fields__:
        if field == "session_id":
            continue
        worker_value = getattr(worker, field)
        if worker_value == getattr(parent, field):
            continue
        if field == "attempt_number":
            if worker_value is not None:
                updates[field] = worker_value
        elif worker_value not in ("", None):
            updates[field] = worker_value
    return updates
