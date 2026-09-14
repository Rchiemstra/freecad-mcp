from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_add_bezier_contract import (
    SketchAddBezierRequest,
    DocumentName,
    SketchName,
    make_sketch_add_bezier_uncertain,
    parse_sketch_add_bezier_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_add_bezier_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    poles: list[dict[str, float]],
    construction: bool = False,
) -> CallToolResult:
    request = SketchAddBezierRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        poles=tuple((float(point['x']), float(point['y'])) for point in poles),
        construction=construction,
    )
    try:
        raw_result: object = freecad.sketch_add_bezier(request.doc_name, request.sketch_name, poles, construction)
    except Exception as exc:
        raw_result = make_sketch_add_bezier_uncertain(
            "SKETCH_ADD_BEZIER_TRANSPORT_UNCERTAIN",
            f"sketch_add_bezier response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_add_bezier_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run sketch_add_bezier: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
