"""Instrumented FastMCP constants and output schema."""

from __future__ import annotations

import inspect

from mcp.server.lowlevel.server import Server

from ..outcomes import NORMALIZED_STATUSES

LOW_LEVEL_ACCEPTS_CALL_TOOL_RESULT = (
    "isinstance(results, types.CallToolResult)"
    in inspect.getsource(Server.call_tool)
)
RESULT_OUTPUT_SCHEMA = {
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

CONTROL_LANE_TOOLS = frozenset(
    {
        "cancel_request",
        "get_request_status",
    }
)
