from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_add_rectangle_contract import (
    SketchAddRectangleRequest,
    DocumentName,
    SketchName,
    make_sketch_add_rectangle_uncertain,
    parse_sketch_add_rectangle_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_add_rectangle_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    construction: bool = False,
) -> CallToolResult:
    request = SketchAddRectangleRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y2,
        construction=construction,
    )
    try:
        raw_result: object = freecad.sketch_add_rectangle(request.doc_name, request.sketch_name, x1, y1, x2, y2, construction)
    except Exception as exc:
        raw_result = make_sketch_add_rectangle_uncertain(
            "SKETCH_ADD_RECTANGLE_TRANSPORT_UNCERTAIN",
            f"sketch_add_rectangle response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_add_rectangle_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run sketch_add_rectangle: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
