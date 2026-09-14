from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.boolean_intersection_contract import (
    make_boolean_intersection_uncertain,
    parse_boolean_intersection_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def boolean_intersection_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str, shape1: str, shape2: str, result_name: str
) -> CallToolResult:
    try:
        raw_result: object = freecad.boolean_intersection(doc_name, shape1, shape2, result_name)
    except Exception as exc:
        raw_result = make_boolean_intersection_uncertain(
            "BOOLEAN_INTERSECTION_TRANSPORT_UNCERTAIN",
            f"BooleanIntersection response unavailable: {exc}",
            committed=None,
        )
    result = parse_boolean_intersection_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to create boolean_intersection: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
