"""FastMCP wrapper that owns call correlation and lifecycle telemetry."""

from __future__ import annotations

# §3.3 compatibility shims — keep old import paths working.
from .instrumented_server_ops.constants import CONTROL_LANE_TOOLS
from .instrumented_server_ops.facade_bindings import bind_instrumented_fast_mcp
from .instrumented_server_ops.helpers import execution_category
from .instrumented_server_ops.instrumented_fast_mcp import InstrumentedFastMCP
from .telemetry import emit_event

bind_instrumented_fast_mcp(InstrumentedFastMCP)

__all__ = [
    "CONTROL_LANE_TOOLS",
    "InstrumentedFastMCP",
    "emit_event",
    "execution_category",
]
