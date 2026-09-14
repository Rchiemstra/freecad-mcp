from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_split_contract import (
    SketchSplitRequest,
    DocumentName,
    SketchName,
    make_sketch_split_uncertain,
    parse_sketch_split_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_split_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    geo_index: int,
    point_x: float,
    point_y: float,
) -> CallToolResult:
    request = SketchSplitRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        geo_index=geo_index,
        point_x=point_x,
        point_y=point_y,
    )
    try:
        raw_result: object = freecad.sketch_split(request.doc_name, request.sketch_name, geo_index, point_x, point_y)
    except Exception as exc:
        raw_result = make_sketch_split_uncertain(
            "SKETCH_SPLIT_TRANSPORT_UNCERTAIN",
            f"sketch_split response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_split_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run sketch_split: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
