from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_constrain_radius_contract import (
    SketchConstrainRadiusRequest,
    DocumentName,
    SketchName,
    make_sketch_constrain_radius_uncertain,
    parse_sketch_constrain_radius_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_constrain_radius_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    geo: int,
    value: float,
    name: str | None = None,
) -> CallToolResult:
    request = SketchConstrainRadiusRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        geo=geo,
        value=value,
        name=name,
    )
    try:
        raw_result: object = freecad.sketch_constrain_radius(request.doc_name, request.sketch_name, geo, value, name)
    except Exception as exc:
        raw_result = make_sketch_constrain_radius_uncertain(
            "SKETCH_CONSTRAIN_RADIUS_TRANSPORT_UNCERTAIN",
            f"sketch_constrain_radius response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_constrain_radius_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run sketch_constrain_radius: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
