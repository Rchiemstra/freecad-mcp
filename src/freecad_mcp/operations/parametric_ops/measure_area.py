from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.measure_area_contract import (
    make_measure_area_uncertain,
    parse_measure_area_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def measure_area_operation(
    freecad: FreeCADConnection,
    doc_name: str, obj_name: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad.measure_area(doc_name, obj_name)
    except Exception as exc:
        raw_result = make_measure_area_uncertain(
            "MEASURE_AREA_TRANSPORT_UNCERTAIN",
            f"measure_area response unavailable: {exc}",
            committed=None,
        )
    result = parse_measure_area_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run measure_area: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=True,
    )
