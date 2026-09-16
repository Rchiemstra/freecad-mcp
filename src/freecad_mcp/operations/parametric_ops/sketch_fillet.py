from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_fillet_contract import (
    SketchFilletRequest,
    DocumentName,
    SketchName,
    make_sketch_fillet_failure,
    make_sketch_fillet_uncertain,
    parse_sketch_fillet_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_fillet_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    geo1: int,
    geo2: int,
    radius: float,
) -> CallToolResult:
    if radius <= 0:
        failure = make_sketch_fillet_failure(
            "INVALID_ARGUMENT",
            "fillet radius must be > 0",
        )
        return tool_fail(
            f"Failed to run sketch_fillet: {failure['error']}",
            structured=dict(failure),
            error_code=failure["error_code"],
        )
    request = SketchFilletRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        geo1=geo1,
        geo2=geo2,
        radius=radius,
    )
    try:
        raw_result: object = freecad.sketch_fillet(request.doc_name, request.sketch_name, geo1, geo2, radius)
    except Exception as exc:
        raw_result = make_sketch_fillet_uncertain(
            "SKETCH_FILLET_TRANSPORT_UNCERTAIN",
            f"sketch_fillet response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_fillet_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run sketch_fillet: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
