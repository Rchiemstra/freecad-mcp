from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.set_color_contract import (
    make_set_color_uncertain,
    parse_set_color_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def set_color_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    r: float,
    g: float,
    b: float,
    transparency: float = 0.0,
) -> CallToolResult:
    try:
        raw_result: object = freecad.set_color(doc_name, obj_name, r, g, b, transparency)
    except Exception as exc:
        raw_result = make_set_color_uncertain(
            "SET_COLOR_TRANSPORT_UNCERTAIN",
            f"set_color response unavailable: {exc}",
            committed=None,
        )
    result = parse_set_color_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run set_color: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
