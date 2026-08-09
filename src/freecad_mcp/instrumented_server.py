"""FastMCP wrapper that owns call correlation and lifecycle telemetry."""

from __future__ import annotations

from .instrumented_server_ops.constants import CONTROL_LANE_TOOLS
from .instrumented_server_ops.helpers import execution_category
from .instrumented_server_ops.instrumented_fast_mcp import InstrumentedFastMCP
from .telemetry.writer import emit_event

__all__ = [
    "CONTROL_LANE_TOOLS",
    "InstrumentedFastMCP",
    "emit_event",
    "execution_category",
]
