from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_extend_contract import (
    SketchExtendRequest,
    DocumentName,
    SketchName,
    make_sketch_extend_uncertain,
    parse_sketch_extend_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_extend_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    geo_index: int,
    increment: float,
    end_point: int = 2,
) -> CallToolResult:
    request = SketchExtendRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        geo_index=geo_index,
        increment=increment,
        end_point=end_point,
    )
    try:
        raw_result: object = freecad.sketch_extend(request.doc_name, request.sketch_name, geo_index, increment, end_point)
    except Exception as exc:
        raw_result = make_sketch_extend_uncertain(
            "SKETCH_EXTEND_TRANSPORT_UNCERTAIN",
            f"sketch_extend response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_extend_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run sketch_extend: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
