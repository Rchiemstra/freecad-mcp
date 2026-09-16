from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_trim_contract import (
    SketchTrimRequest,
    DocumentName,
    SketchName,
    make_sketch_trim_uncertain,
    parse_sketch_trim_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_trim_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    geo_index: int,
    point_x: float,
    point_y: float,
) -> CallToolResult:
    request = SketchTrimRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        geo_index=geo_index,
        point_x=point_x,
        point_y=point_y,
    )
    try:
        raw_result: object = freecad.sketch_trim(request.doc_name, request.sketch_name, geo_index, point_x, point_y)
    except Exception as exc:
        raw_result = make_sketch_trim_uncertain(
            "SKETCH_TRIM_TRANSPORT_UNCERTAIN",
            f"sketch_trim response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_trim_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run sketch_trim: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
