from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_offset_contract import (
    DocumentName,
    SketchName,
    SketchOffsetRequest,
    make_sketch_offset_failure,
    make_sketch_offset_uncertain,
    parse_sketch_offset_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_offset_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    geo_indices: list[int],
    offset: float,
    copy: bool = True,
    construction: bool = False,
) -> CallToolResult:
    if offset == 0:
        failure = make_sketch_offset_failure(
            "INVALID_ARGUMENT",
            "offset must be nonzero",
        )
        return tool_fail(
            f"Failed to run sketch_offset: {failure['error']}",
            structured=dict(failure),
            error_code=failure["error_code"],
        )
    request = SketchOffsetRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        geo_indices=tuple(geo_indices),
        offset=offset,
        copy=copy,
        construction=construction,
    )
    try:
        raw_result: object = freecad.sketch_offset(
            request.doc_name,
            request.sketch_name,
            geo_indices,
            offset,
            copy,
            construction,
        )
    except Exception as exc:
        raw_result = make_sketch_offset_uncertain(
            "SKETCH_OFFSET_TRANSPORT_UNCERTAIN",
            f"sketch_offset response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_offset_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run sketch_offset: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
