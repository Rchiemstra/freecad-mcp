"""Async call_tool instrumentation for InstrumentedFastMCP."""

from __future__ import annotations

import time
from typing import Any

from ..telemetry import bind_context
from .call_tool_helpers import (
    emit_tool_completion_event,
    emit_validation_events,
    extract_call_metadata,
    invoke_registered_tool,
)
from .surfaces import emit_event


async def call_tool_impl(self, name: str, arguments: dict[str, Any]):
    context = self.get_context()
    call_id, task_id, parent_call_id, attempt, category = extract_call_metadata(
        context, name
    )
    started = time.monotonic()
    with bind_context(
        task_id=task_id,
        call_id=call_id,
        attempt_number=attempt,
        parent_call_id=parent_call_id,
        operation=name,
        execution_category=category,
    ):
        emit_event(
            "mcp",
            "tool_call_received",
            payload={
                "tool": name,
                "arguments": arguments,
                "execution_category": category,
            },
        )
        emit_validation_events(self, name, arguments)
        result = None
        tool_exc: BaseException | None = None
        try:
            result = await invoke_registered_tool(self, context, name, arguments)
        except BaseException as exc:
            tool_exc = exc
        finally:
            duration_ms = (time.monotonic() - started) * 1000.0
            emit_tool_completion_event(
                name=name,
                category=category,
                result=result,
                tool_exc=tool_exc,
                duration_ms=duration_ms,
            )
            await self._run_post_tool_completed_hook((time.monotonic() - started), name)

        if tool_exc is not None:
            raise tool_exc
        return self._wire_result(result)
