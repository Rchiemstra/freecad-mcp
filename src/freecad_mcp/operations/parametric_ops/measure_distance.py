from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.measure_distance_contract import (
    make_measure_distance_uncertain,
    parse_measure_distance_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def measure_distance_operation(
    freecad: FreeCADConnection,
    doc_name: str, shape1_ref: str, shape2_ref: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad.measure_distance(doc_name, shape1_ref, shape2_ref)
    except Exception as exc:
        raw_result = make_measure_distance_uncertain(
            "MEASURE_DISTANCE_TRANSPORT_UNCERTAIN",
            f"measure_distance response unavailable: {exc}",
            committed=None,
        )
    result = parse_measure_distance_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run measure_distance: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=True,
    )
