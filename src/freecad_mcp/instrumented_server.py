"""FastMCP wrapper that owns call correlation and lifecycle telemetry."""

from __future__ import annotations

import asyncio
import contextvars
import inspect
import time
import uuid
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.lowlevel.server import Server
from mcp.types import CallToolResult

from .mcp_tasks import HEAVY_TASK_TOOLS, finish, register
from .mcp_tasks import get as get_task_link
from .outcomes import NORMALIZED_STATUSES, OutcomeStatus, extract_error_code
from .telemetry import bind_context, emit_event
from .telemetry.context import TelemetryContext, get_context, update_context

_LOW_LEVEL_ACCEPTS_CALL_TOOL_RESULT = (
    "isinstance(results, types.CallToolResult)"
    in inspect.getsource(Server.call_tool)
)
_RESULT_OUTPUT_SCHEMA = {
    "title": "FreeCADMCPResultEnvelope",
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "schema_version": {"const": 1},
        "status": {"enum": sorted(NORMALIZED_STATUSES)},
        "operation": {"type": "string"},
        "message": {"type": "string"},
        "error": {"type": ["string", "null"]},
        "error_code": {"type": ["string", "null"]},
        "correlation": {"type": "object"},
        "layers": {"type": "object"},
        "data": {},
    },
    "required": [
        "schema_version",
        "status",
        "operation",
        "message",
        "error",
        "error_code",
        "correlation",
        "layers",
        "data",
    ],
}


def _meta_values(context: Any) -> dict[str, Any]:
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


def _first(values: Mapping[str, Any], *names: str) -> Any:
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


# Bounded MCP tools that must not queue behind long-running synchronous work.
# D6 requires cancel_request on an isolated lane so in-flight work can be
# interrupted without waiting behind execute_code / acquire / release. Custody
# tools such as claim_acquisition_result mutate shared session/token state and
# must stay on the general serialized lane to avoid racing those operations.
CONTROL_LANE_TOOLS = frozenset(
    {
        "cancel_request",
        "get_request_status",
    }
)


def _worker_context_updates(
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


class _SerializedWorkerLane:
    """Single-thread executor that keeps sync tool bodies off the event loop."""

    def __init__(self, *, thread_name_prefix: str) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=thread_name_prefix,
        )

    async def run(self, func: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
        parent_ctx = get_context()
        ctx = contextvars.copy_context()
        loop = asyncio.get_running_loop()

        def _invoke() -> tuple[Any, TelemetryContext, BaseException | None]:
            worker_ctx = parent_ctx
            result: Any = None
            exc: BaseException | None = None

            def _run_in_copied_context() -> None:
                nonlocal worker_ctx, result, exc
                try:
                    result = func(*args, **kwargs)
                except BaseException as raised:
                    exc = raised
                finally:
                    worker_ctx = get_context()

            ctx.run(_run_in_copied_context)
            return result, worker_ctx, exc

        result, worker_ctx, exc = await loop.run_in_executor(self._executor, _invoke)
        updates = _worker_context_updates(parent_ctx, worker_ctx)
        if updates:
            update_context(**updates)
        if exc is not None:
            raise exc
        return result


def _invoke_sync_tool(tool: Any, arguments: dict[str, Any], context: Any) -> Any:
    """Run one synchronous tool with the MCP SDK's argument validation."""

    metadata = tool.fn_metadata
    context_kwargs = (
        {tool.context_kwarg: context}
        if tool.context_kwarg is not None
        else None
    )
    arguments_pre_parsed = metadata.pre_parse_json(arguments)
    arguments_parsed_model = metadata.arg_model.model_validate(
        arguments_pre_parsed
    )
    arguments_parsed_dict = arguments_parsed_model.model_dump_one_level()
    arguments_parsed_dict |= context_kwargs or {}
    return tool.fn(**arguments_parsed_dict)


class InstrumentedFastMCP(FastMCP):
    task_request_canceller: Callable[[str], Any] | None = None
    post_tool_completed_hook: Callable[[float, str], Any] | None = None
    _sync_worker_lane: _SerializedWorkerLane | None = None
    _control_worker_lane: _SerializedWorkerLane | None = None

    def _sync_lane(self) -> _SerializedWorkerLane:
        lane = self._sync_worker_lane
        if lane is None:
            lane = _SerializedWorkerLane(thread_name_prefix="mcp-sync-tool")
            self._sync_worker_lane = lane
        return lane

    def _control_lane(self) -> _SerializedWorkerLane:
        lane = self._control_worker_lane
        if lane is None:
            lane = _SerializedWorkerLane(thread_name_prefix="mcp-control-tool")
            self._control_worker_lane = lane
        return lane

    def _worker_lane_for_tool(self, name: str) -> _SerializedWorkerLane:
        if name in CONTROL_LANE_TOOLS:
            return self._control_lane()
        return self._sync_lane()

    def add_tool(
        self,
        fn,
        name=None,
        title=None,
        description=None,
        annotations=None,
        structured_output=None,
        **kwargs,
    ) -> None:
        """Register tools with the schema of their structured MCP envelope.

        A Python return annotation of ``CallToolResult`` describes the complete
        protocol response, not its ``structuredContent``. Some MCP SDK releases
        incorrectly advertise that model as the tool output schema. Replacing
        only that inferred schema makes validation and discovery describe the
        actual schema-v1 envelope.
        """

        options = {
            "name": name,
            "title": title,
            "description": description,
            "annotations": annotations,
            "structured_output": structured_output,
            **kwargs,
        }
        supported = inspect.signature(FastMCP.add_tool).parameters
        FastMCP.add_tool(
            self,
            fn,
            **{key: value for key, value in options.items() if key in supported},
        )
        registered = self._tool_manager.get_tool(name or fn.__name__)
        metadata = getattr(registered, "fn_metadata", None)
        schema = getattr(metadata, "output_schema", None)
        return_annotation = inspect.signature(fn).return_annotation
        returns_call_tool_result = (
            return_annotation is CallToolResult
            or str(return_annotation).strip("'\"").endswith("CallToolResult")
        )
        if returns_call_tool_result and (
            schema is None
            or (
                isinstance(schema, Mapping)
                and schema.get("title") == "CallToolResult"
            )
        ):
            metadata.output_schema = dict(_RESULT_OUTPUT_SCHEMA)

    def create_initialization_options(self):
        """Expose the low-level server contract used by MCP memory transports.

        Recent MCP SDKs keep this method on ``FastMCP._mcp_server`` while older
        test/client helpers accepted the FastMCP wrapper itself.  Delegation
        preserves both interfaces without bypassing the registered FastMCP
        call handlers or this class's instrumentation.
        """

        return self._mcp_server.create_initialization_options()

    def run(self, transport="stdio", mount_path=None, *args, **kwargs):
        """Run either FastMCP transport mode or the low-level stream contract."""

        if not isinstance(transport, str):
            return self._mcp_server.run(
                transport,
                mount_path,
                *args,
                **kwargs,
            )
        return super().run(transport=transport, mount_path=mount_path)

    async def _call_registered_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> Any:
        """Get the tool's native result before SDK result conversion.

        MCP SDK 1.26 serializes a ``CallToolResult`` as a nested JSON value when
        FastMCP's conversion path is used, while newer SDKs pass it through.
        Calling the registered tool without conversion gives both versions the
        same authoritative result for telemetry and wire adaptation.

        Synchronous tool bodies run on a serialized worker lane so the asyncio
        event loop stays responsive for lease heartbeats and other scheduled
        coroutines. Bounded control tools use a separate lane so cancellation
        and status polling are not queued behind long-running work.
        """

        context = self.get_context()
        tool = self._tool_manager.get_tool(name)
        if tool is None:
            raise ToolError(f"Unknown tool: {name}")

        if tool.is_async:
            try:
                return await self._tool_manager.call_tool(
                    name,
                    arguments,
                    context=context,
                    convert_result=False,
                )
            except TypeError:
                return await self._tool_manager.call_tool(
                    name,
                    arguments,
                    context=context,
                )

        lane = self._worker_lane_for_tool(name)

        def _run_sync() -> Any:
            try:
                return _invoke_sync_tool(tool, arguments, context)
            except ToolError:
                raise
            except Exception as exc:
                raise ToolError(
                    f"Error executing tool {name}: {exc}"
                ) from exc

        return await lane.run(_run_sync)

    @staticmethod
    def _wire_result(result: Any) -> Any:
        if (
            isinstance(result, CallToolResult)
            and not _LOW_LEVEL_ACCEPTS_CALL_TOOL_RESULT
        ):
            if result.structuredContent is not None:
                return (result.content, result.structuredContent)
            return result.content
        return result

    async def _run_post_tool_completed_hook(
        self, duration_s: float, tool_name: str
    ) -> None:
        """Best-effort stale recovery hook; never fail the tool outcome."""

        hook = self.post_tool_completed_hook
        if hook is None:
            return
        try:
            hook_result = hook(duration_s, tool_name)
            if inspect.isawaitable(hook_result):
                await hook_result
        except Exception as exc:
            emit_event(
                "mcp",
                "post_tool_recovery_failed",
                status=OutcomeStatus.WARNING.value,
                error_code=type(exc).__name__.upper(),
                payload={
                    "tool": tool_name,
                    "exception_type": type(exc).__name__,
                },
            )

    async def call_tool(self, name: str, arguments: dict[str, Any]):
        context = self.get_context()
        metadata = _meta_values(context)
        try:
            protocol_call_id = context.request_id
        except (AttributeError, ValueError):
            protocol_call_id = str(uuid.uuid4())
        call_id = str(
            _first(
                metadata,
                "call_id",
                "tool_use_id",
                "toolUseId",
                "io.modelcontextprotocol/call-id",
            )
            or protocol_call_id
        )
        task_id = str(
            _first(
                metadata,
                "task_id",
                "taskId",
                "io.modelcontextprotocol/task-id",
            )
            or ""
        )
        parent_call_id = str(
            _first(metadata, "parent_call_id", "parentCallId") or ""
        )
        attempt = _first(metadata, "attempt_number", "attemptNumber", "attempt")
        started = time.monotonic()
        category = execution_category(name)
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
            emit_event(
                "mcp",
                "validation_started",
                payload={"tool": name},
            )
            validation_started = time.monotonic()
            try:
                registered = self._tool_manager.get_tool(name)
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
                    error_code=extract_error_code(exc)
                    or "INVALID_ARGUMENT",
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
            result = None
            tool_exc: BaseException | None = None
            try:
                experimental = getattr(
                    getattr(context, "request_context", None),
                    "experimental",
                    None,
                )
                task_metadata = getattr(experimental, "task_metadata", None)
                if (
                    name in HEAVY_TASK_TOOLS
                    and task_metadata is not None
                    and callable(getattr(experimental, "run_task", None))
                ):
                    async def work(task_context):
                        task_id_value = str(task_context.task.taskId)
                        register(task_id_value, name)
                        with bind_context(task_id=task_id_value):
                            try:
                                task_result = await self._call_registered_tool(
                                    name, arguments
                                )
                            except BaseException as exc:
                                cancelled = isinstance(
                                    exc, asyncio.CancelledError
                                )
                                finish(
                                    task_id_value,
                                    "cancelled" if cancelled else "failed",
                                )
                                if cancelled:
                                    link = get_task_link(task_id_value) or {}
                                    request_id = str(
                                        link.get("request_id") or ""
                                    )
                                    if (
                                        request_id
                                        and callable(
                                            self.task_request_canceller
                                        )
                                    ):
                                        try:
                                            await asyncio.to_thread(
                                                self.task_request_canceller,
                                                request_id,
                                            )
                                        except Exception as cancel_exc:
                                            emit_event(
                                                "mcp_tasks",
                                                "cancellation_acknowledged",
                                                status=OutcomeStatus.WARNING.value,
                                                error_code=(
                                                    extract_error_code(
                                                        cancel_exc
                                                    )
                                                    or type(
                                                        cancel_exc
                                                    ).__name__.upper()
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

                    result = await experimental.run_task(
                        work,
                        model_immediate_response=(
                            f"{name} is running as an MCP task"
                        ),
                    )
                else:
                    result = await self._call_registered_tool(name, arguments)
            except BaseException as exc:
                tool_exc = exc
            finally:
                duration_s = time.monotonic() - started
                duration_ms = duration_s * 1000.0
                if tool_exc is not None:
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
                    elif isinstance(tool_exc, Exception):
                        code = (
                            extract_error_code(tool_exc)
                            or type(tool_exc).__name__.upper()
                        )
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
                else:
                    status = OutcomeStatus.SUCCEEDED.value
                    code = None
                    completion_payload: dict[str, Any] = {
                        "tool": name,
                        "execution_category": category,
                    }
                    if isinstance(result, CallToolResult):
                        structured = result.structuredContent
                        if isinstance(structured, Mapping):
                            status = str(
                                structured.get("status")
                                or OutcomeStatus.UNKNOWN.value
                            )
                            code = extract_error_code(structured)
                            data = structured.get("data")
                            actual_category = structured.get(
                                "execution_category"
                            )
                            if (
                                actual_category is None
                                and isinstance(data, Mapping)
                            ):
                                actual_category = data.get(
                                    "execution_category"
                                )
                            if actual_category:
                                completion_payload["execution_category"] = str(
                                    actual_category
                                )
                            analysis = structured.get("code_analysis")
                            if (
                                analysis is None
                                and isinstance(data, Mapping)
                            ):
                                analysis = data.get("code_analysis")
                            if isinstance(analysis, Mapping):
                                completion_payload["analysis"] = dict(analysis)
                        elif result.isError:
                            status = OutcomeStatus.FAILED.value
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
                await self._run_post_tool_completed_hook(duration_s, name)

            if tool_exc is not None:
                raise tool_exc
            return self._wire_result(result)


__all__ = [
    "CONTROL_LANE_TOOLS",
    "InstrumentedFastMCP",
    "execution_category",
]
