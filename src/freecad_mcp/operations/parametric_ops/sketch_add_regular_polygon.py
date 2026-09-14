from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_add_regular_polygon_contract import (
    SketchAddRegularPolygonRequest,
    DocumentName,
    SketchName,
    make_sketch_add_regular_polygon_failure,
    make_sketch_add_regular_polygon_uncertain,
    parse_sketch_add_regular_polygon_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_add_regular_polygon_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    cx: float,
    cy: float,
    radius: float,
    sides: int,
    angle: float = 0.0,
    construction: bool = False,
) -> CallToolResult:
    if sides < 3:
        failure = make_sketch_add_regular_polygon_failure(
            "INVALID_ARGUMENT",
            "regular polygon requires at least 3 sides",
        )
        return tool_fail(
            f"Failed to run sketch_add_regular_polygon: {failure['error']}",
            structured=dict(failure),
            error_code=failure["error_code"],
        )
    request = SketchAddRegularPolygonRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        cx=cx,
        cy=cy,
        radius=radius,
        sides=sides,
        angle=angle,
        construction=construction,
    )
    try:
        raw_result: object = freecad.sketch_add_regular_polygon(request.doc_name, request.sketch_name, cx, cy, radius, sides, angle, construction)
    except Exception as exc:
        raw_result = make_sketch_add_regular_polygon_uncertain(
            "SKETCH_ADD_REGULAR_POLYGON_TRANSPORT_UNCERTAIN",
            f"sketch_add_regular_polygon response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_add_regular_polygon_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run sketch_add_regular_polygon: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
