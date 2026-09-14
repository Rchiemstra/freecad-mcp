from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_add_bspline_through_points_contract import (
    SketchAddBsplineThroughPointsRequest,
    DocumentName,
    SketchName,
    make_sketch_add_bspline_through_points_uncertain,
    parse_sketch_add_bspline_through_points_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_add_bspline_through_points_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    points: list[dict[str, float]],
    degree: int = 3,
    periodic: bool = False,
    construction: bool = False,
) -> CallToolResult:
    request = SketchAddBsplineThroughPointsRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        points=points,
        degree=degree,
        periodic=periodic,
        construction=construction,
    )
    try:
        raw_result: object = freecad.sketch_add_bspline_through_points(request.doc_name, request.sketch_name, points, degree, periodic, construction)
    except Exception as exc:
        raw_result = make_sketch_add_bspline_through_points_uncertain(
            "SKETCH_ADD_BSPLINE_THROUGH_POINTS_TRANSPORT_UNCERTAIN",
            f"sketch_add_bspline_through_points response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_add_bspline_through_points_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run sketch_add_bspline_through_points: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
