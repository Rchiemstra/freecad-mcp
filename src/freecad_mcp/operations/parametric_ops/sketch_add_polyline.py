from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_add_polyline_contract import (
    SketchAddPolylineRequest,
    DocumentName,
    SketchName,
    make_sketch_add_polyline_failure,
    make_sketch_add_polyline_uncertain,
    parse_sketch_add_polyline_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_add_polyline_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    points: list[dict[str, float]],
    closed: bool = False,
    construction: bool = False,
) -> CallToolResult:
    if len(points) < 2:
        failure = make_sketch_add_polyline_failure(
            "INVALID_ARGUMENT",
            "polyline requires at least 2 points",
        )
        return tool_fail(
            f"Failed to run sketch_add_polyline: {failure['error']}",
            structured=dict(failure),
            error_code=failure["error_code"],
        )
    request = SketchAddPolylineRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        points=points,
        closed=closed,
        construction=construction,
    )
    try:
        raw_result: object = freecad.sketch_add_polyline(request.doc_name, request.sketch_name, points, closed, construction)
    except Exception as exc:
        raw_result = make_sketch_add_polyline_uncertain(
            "SKETCH_ADD_POLYLINE_TRANSPORT_UNCERTAIN",
            f"sketch_add_polyline response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_add_polyline_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run sketch_add_polyline: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
