"""InstrumentedFastMCP method implementations (bound on the class)."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import CallToolResult

from ..outcomes import OutcomeStatus
from .constants import CONTROL_LANE_TOOLS, LOW_LEVEL_ACCEPTS_CALL_TOOL_RESULT, RESULT_OUTPUT_SCHEMA
from .serialized_worker_lane import SerializedWorkerLane
from .surfaces import emit_event
from .sync_tool_invoke import invoke_sync_tool


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
            metadata.output_schema = dict(RESULT_OUTPUT_SCHEMA)

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
                return invoke_sync_tool(tool, arguments, context)
            except ToolError:
                raise
            except Exception as exc:
                raise ToolError(
                    f"Error executing tool {name}: {exc}"
                ) from exc

        return await lane.run(_run_sync)

def _wire_result(result: Any) -> Any:
        if (
            isinstance(result, CallToolResult)
            and not LOW_LEVEL_ACCEPTS_CALL_TOOL_RESULT
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

def _sync_lane(self) -> SerializedWorkerLane:
        lane = self._sync_worker_lane
        if lane is None:
            lane = SerializedWorkerLane(thread_name_prefix="mcp-sync-tool")
            self._sync_worker_lane = lane
        return lane

def _control_lane(self) -> SerializedWorkerLane:
        lane = self._control_worker_lane
        if lane is None:
            lane = SerializedWorkerLane(thread_name_prefix="mcp-control-tool")
            self._control_worker_lane = lane
        return lane

def _worker_lane_for_tool(self, name: str) -> SerializedWorkerLane:
        if name in CONTROL_LANE_TOOLS:
            return self._control_lane()
        return self._sync_lane()
