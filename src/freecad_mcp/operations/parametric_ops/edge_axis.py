from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.edge_axis_contract import (
    make_edge_axis_uncertain,
    parse_edge_axis_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def edge_axis_operation(
    freecad: FreeCADConnection,
    doc_name: str, object_name: str, edge: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad.edge_axis(doc_name, object_name, edge)
    except Exception as exc:
        raw_result = make_edge_axis_uncertain(
            "EDGE_AXIS_TRANSPORT_UNCERTAIN",
            f"edge_axis response unavailable: {exc}",
            committed=None,
        )
    result = parse_edge_axis_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run edge_axis: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=True,
    )
