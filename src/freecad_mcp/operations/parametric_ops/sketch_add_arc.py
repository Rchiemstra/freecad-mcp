from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_add_arc_contract import (
    SketchAddArcRequest,
    DocumentName,
    SketchName,
    make_sketch_add_arc_uncertain,
    parse_sketch_add_arc_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_add_arc_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    cx: float,
    cy: float,
    radius: float,
    start_angle: float,
    end_angle: float,
    construction: bool = False,
) -> CallToolResult:
    request = SketchAddArcRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        cx=cx,
        cy=cy,
        radius=radius,
        start_angle=start_angle,
        end_angle=end_angle,
        construction=construction,
    )
    try:
        raw_result: object = freecad.sketch_add_arc(request.doc_name, request.sketch_name, cx, cy, radius, start_angle, end_angle, construction)
    except Exception as exc:
        raw_result = make_sketch_add_arc_uncertain(
            "SKETCH_ADD_ARC_TRANSPORT_UNCERTAIN",
            f"sketch_add_arc response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_add_arc_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run sketch_add_arc: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
