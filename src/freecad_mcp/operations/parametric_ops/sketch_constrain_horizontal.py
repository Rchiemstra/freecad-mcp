from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_constrain_horizontal_contract import (
    SketchConstrainHorizontalRequest,
    DocumentName,
    SketchName,
    make_sketch_constrain_horizontal_uncertain,
    parse_sketch_constrain_horizontal_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_constrain_horizontal_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    geo: int,
) -> CallToolResult:
    request = SketchConstrainHorizontalRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        geo=geo,
    )
    try:
        raw_result: object = freecad.sketch_constrain_horizontal(request.doc_name, request.sketch_name, geo)
    except Exception as exc:
        raw_result = make_sketch_constrain_horizontal_uncertain(
            "SKETCH_CONSTRAIN_HORIZONTAL_TRANSPORT_UNCERTAIN",
            f"sketch_constrain_horizontal response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_constrain_horizontal_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run sketch_constrain_horizontal: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
