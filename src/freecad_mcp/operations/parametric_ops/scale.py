from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.scale_contract import (
    ScaleRequest,
    make_scale_uncertain,
    parse_scale_response,
    DocumentName,
    ObjectName,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def scale_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    sx: float,
    sy: float,
    sz: float,
) -> CallToolResult:
    request = ScaleRequest(
        doc_name=DocumentName(doc_name),
        obj_name=ObjectName(obj_name),
        sx=sx,
        sy=sy,
        sz=sz
    )
    try:
        raw_result: object = freecad.scale(doc_name, obj_name, sx, sy, sz)
    except Exception as exc:
        raw_result = make_scale_uncertain(
            "SCALE_TRANSPORT_UNCERTAIN",
            f"Scale response unavailable: {exc}",
            committed=None,
        )
    result = parse_scale_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run scale: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
