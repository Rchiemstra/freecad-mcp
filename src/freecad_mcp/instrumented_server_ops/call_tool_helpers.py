"""Helpers for InstrumentedFastMCP.call_tool instrumentation."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Mapping
from typing import Any

from mcp.types import CallToolResult

from ..mcp_tasks import HEAVY_TASK_TOOLS, finish, register
from ..mcp_tasks import get as get_task_link
from ..outcomes import OutcomeStatus, extract_error_code
from ..telemetry import bind_context
from .helpers import execution_category, first, meta_values
from .surfaces import emit_event


def extract_call_metadata(context, name: str) -> tuple[str, str, str, Any, str]:
    metadata = meta_values(context)
    try:
        protocol_call_id = context.request_id
    except (AttributeError, ValueError):
        protocol_call_id = str(uuid.uuid4())
    call_id = str(
        first(
            metadata,
            "call_id",
            "tool_use_id",
            "toolUseId",
            "io.modelcontextprotocol/call-id",
        )
        or protocol_call_id
    )
    task_id = str(
        first(
            metadata,
            "task_id",
            "taskId",
            "io.modelcontextprotocol/task-id",
        )
        or ""
    )
    parent_call_id = str(first(metadata, "parent_call_id", "parentCallId") or "")
    attempt = first(metadata, "attempt_number", "attemptNumber", "attempt")
    return call_id, task_id, parent_call_id, attempt, execution_category(name)


def emit_validation_events(
    server,
    name: str,
    arguments: dict[str, Any],
) -> None:
    emit_event("mcp", "validation_started", payload={"tool": name})
    validation_started = time.monotonic()
    try:
        registered = server._tool_manager.get_tool(name)
        metadata_model = getattr(
            getattr(registered, "fn_metadata", None),
            "arg_model",
            None,
        )
        if metadata_model is not None:
            metadata_model.model_validate(arguments)
    except Exception as exc:
        emit_event(
            "mcp",
            "validation_completed",
            status=OutcomeStatus.REJECTED.value,
            duration_ms=(time.monotonic() - validation_started) * 1000.0,
            error_code=extract_error_code(exc) or "INVALID_ARGUMENT",
            payload={
                "tool": name,
                "exception_type": type(exc).__name__,
            },
        )
    else:
        emit_event(
            "mcp",
            "validation_completed",
            duration_ms=(time.monotonic() - validation_started) * 1000.0,
            payload={"tool": name},
        )


async def invoke_registered_tool(server, context, name: str, arguments: dict[str, Any]):
    experimental = getattr(
        getattr(context, "request_context", None),
        "experimental",
        None,
    )
    task_metadata = getattr(experimental, "task_metadata", None)
    if (
        name not in HEAVY_TASK_TOOLS
        or task_metadata is None
        or not callable(getattr(experimental, "run_task", None))
    ):
        return await server._call_registered_tool(name, arguments)

    async def work(task_context):
        task_id_value = str(task_context.task.taskId)
        register(task_id_value, name)
        with bind_context(task_id=task_id_value):
            try:
                task_result = await server._call_registered_tool(name, arguments)
            except BaseException as exc:
                cancelled = isinstance(exc, asyncio.CancelledError)
                finish(task_id_value, "cancelled" if cancelled else "failed")
                if cancelled:
                    link = get_task_link(task_id_value) or {}
                    request_id = str(link.get("request_id") or "")
                    if request_id and callable(server.task_request_canceller):
                        try:
                            await asyncio.to_thread(
                                server.task_request_canceller,
                                request_id,
                            )
                        except Exception as cancel_exc:
                            emit_event(
                                "mcp_tasks",
                                "cancellation_acknowledged",
                                status=OutcomeStatus.WARNING.value,
                                error_code=(
                                    extract_error_code(cancel_exc)
                                    or type(cancel_exc).__name__.upper()
                                ),
                                payload={
                                    "task_id": task_id_value,
                                    "request_id": request_id,
                                    "bridge_failed": True,
                                },
                            )
                raise
            finish(task_id_value, "completed")
            return task_result

    return await experimental.run_task(
        work,
        model_immediate_response=f"{name} is running as an MCP task",
    )


def emit_tool_exception_completion(
    *,
    name: str,
    tool_exc: BaseException,
    duration_ms: float,
) -> None:
    if isinstance(tool_exc, asyncio.CancelledError):
        emit_event(
            "mcp",
            "tool_call_completed",
            status=OutcomeStatus.CANCELLED.value,
            duration_ms=duration_ms,
            error_code="CANCELLED",
            payload={
                "tool": name,
                "exception_type": type(tool_exc).__name__,
            },
        )
        return
    if isinstance(tool_exc, Exception):
        code = extract_error_code(tool_exc) or type(tool_exc).__name__.upper()
        emit_event(
            "mcp",
            "tool_call_completed",
            status=OutcomeStatus.FAILED.value,
            duration_ms=duration_ms,
            error_code=code,
            payload={
                "tool": name,
                "exception_type": type(tool_exc).__name__,
            },
        )


def build_tool_success_completion(
    *,
    name: str,
    category: str,
    result: Any,
) -> tuple[str, str | None, dict[str, Any]]:
    status = OutcomeStatus.SUCCEEDED.value
    code = None
    completion_payload: dict[str, Any] = {
        "tool": name,
        "execution_category": category,
    }
    if not isinstance(result, CallToolResult):
        return status, code, completion_payload
    structured = result.structuredContent
    if isinstance(structured, Mapping):
        status = str(structured.get("status") or OutcomeStatus.UNKNOWN.value)
        code = extract_error_code(structured)
        data = structured.get("data")
        actual_category = structured.get("execution_category")
        if actual_category is None and isinstance(data, Mapping):
            actual_category = data.get("execution_category")
        if actual_category:
            completion_payload["execution_category"] = str(actual_category)
        analysis = structured.get("code_analysis")
        if analysis is None and isinstance(data, Mapping):
            analysis = data.get("code_analysis")
        if isinstance(analysis, Mapping):
            completion_payload["analysis"] = dict(analysis)
    elif result.isError:
        status = OutcomeStatus.FAILED.value
    return status, code, completion_payload


def emit_tool_completion_event(
    *,
    name: str,
    category: str,
    result: Any,
    tool_exc: BaseException | None,
    duration_ms: float,
) -> None:
    if tool_exc is not None:
        emit_tool_exception_completion(
            name=name,
            tool_exc=tool_exc,
            duration_ms=duration_ms,
        )
        return

    status, code, completion_payload = build_tool_success_completion(
        name=name,
        category=category,
        result=result,
    )
    if status == OutcomeStatus.REJECTED.value:
        emit_event(
            "mcp",
            "policy_rejected",
            status=status,
            error_code=code,
            payload={
                "tool": name,
                "execution_category": category,
            },
        )
    emit_event(
        "mcp",
        "tool_call_completed",
        status=status,
        duration_ms=duration_ms,
        error_code=code,
        payload=completion_payload,
    )
