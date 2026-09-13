from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_constrain_parallel_contract import (
    SketchConstrainParallelRequest,
    DocumentName,
    SketchName,
    make_sketch_constrain_parallel_uncertain,
    parse_sketch_constrain_parallel_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_constrain_parallel_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    geo1: int,
    geo2: int,
) -> CallToolResult:
    request = SketchConstrainParallelRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        geo1=geo1,
        geo2=geo2,
    )
    try:
        raw_result: object = freecad.sketch_constrain_parallel(request.doc_name, request.sketch_name, geo1, geo2)
    except Exception as exc:
        raw_result = make_sketch_constrain_parallel_uncertain(
            "SKETCH_CONSTRAIN_PARALLEL_TRANSPORT_UNCERTAIN",
            f"sketch_constrain_parallel response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_constrain_parallel_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run sketch_constrain_parallel: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
