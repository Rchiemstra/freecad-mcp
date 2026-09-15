from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.get_global_shape_contract import (
    make_get_global_shape_uncertain,
    parse_get_global_shape_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def get_global_shape_operation(
    freecad: FreeCADConnection,
    doc_name: str, obj_name: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad.get_global_shape(doc_name, obj_name)
    except Exception as exc:
        raw_result = make_get_global_shape_uncertain(
            "GET_GLOBAL_SHAPE_TRANSPORT_UNCERTAIN",
            f"get_global_shape response unavailable: {exc}",
            committed=None,
        )
    result = parse_get_global_shape_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run get_global_shape: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=True,
    )
