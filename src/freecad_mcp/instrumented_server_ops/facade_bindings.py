"""Late-bound method attachments for InstrumentedFastMCP."""

from __future__ import annotations

from .call_tool_ops import call_tool_impl
from .instrumented_methods import (
    _call_registered_tool,
    _control_lane,
    _run_post_tool_completed_hook,
    _sync_lane,
    _wire_result,
    _worker_lane_for_tool,
    add_tool,
    create_initialization_options,
    run,
)


def bind_instrumented_fast_mcp(InstrumentedFastMCP):
    InstrumentedFastMCP.add_tool = add_tool
    InstrumentedFastMCP.create_initialization_options = create_initialization_options
    InstrumentedFastMCP.run = run
    InstrumentedFastMCP._call_registered_tool = _call_registered_tool
    InstrumentedFastMCP._wire_result = staticmethod(_wire_result)
    InstrumentedFastMCP._run_post_tool_completed_hook = _run_post_tool_completed_hook
    InstrumentedFastMCP._sync_lane = _sync_lane
    InstrumentedFastMCP._control_lane = _control_lane
    InstrumentedFastMCP._worker_lane_for_tool = _worker_lane_for_tool
    InstrumentedFastMCP.call_tool = call_tool_impl
