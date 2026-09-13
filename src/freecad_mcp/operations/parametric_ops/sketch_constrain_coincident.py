from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_constrain_coincident_contract import (
    SketchConstrainCoincidentRequest,
    DocumentName,
    SketchName,
    make_sketch_constrain_coincident_uncertain,
    parse_sketch_constrain_coincident_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_constrain_coincident_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    geo1: int,
    pos1: int,
    geo2: int,
    pos2: int,
) -> CallToolResult:
    request = SketchConstrainCoincidentRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        geo1=geo1,
        pos1=pos1,
        geo2=geo2,
        pos2=pos2,
    )
    try:
        raw_result: object = freecad.sketch_constrain_coincident(request.doc_name, request.sketch_name, geo1, pos1, geo2, pos2)
    except Exception as exc:
        raw_result = make_sketch_constrain_coincident_uncertain(
            "SKETCH_CONSTRAIN_COINCIDENT_TRANSPORT_UNCERTAIN",
            f"sketch_constrain_coincident response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_constrain_coincident_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run sketch_constrain_coincident: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
