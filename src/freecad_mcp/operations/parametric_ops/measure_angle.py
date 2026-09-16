from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.measure_angle_contract import (
    make_measure_angle_uncertain,
    parse_measure_angle_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def measure_angle_operation(
    freecad: FreeCADConnection,
    doc_name: str, edge1_ref: str, edge2_ref: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad.measure_angle(doc_name, edge1_ref, edge2_ref)
    except Exception as exc:
        raw_result = make_measure_angle_uncertain(
            "MEASURE_ANGLE_TRANSPORT_UNCERTAIN",
            f"measure_angle response unavailable: {exc}",
            committed=None,
        )
    result = parse_measure_angle_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run measure_angle: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=True,
    )
