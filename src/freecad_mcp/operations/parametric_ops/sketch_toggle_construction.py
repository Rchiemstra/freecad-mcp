from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_toggle_construction_contract import (
    SketchToggleConstructionRequest,
    DocumentName,
    SketchName,
    make_sketch_toggle_construction_uncertain,
    parse_sketch_toggle_construction_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_toggle_construction_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    geo_indices: list[int],
    construction: bool = False,
) -> CallToolResult:
    request = SketchToggleConstructionRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        geo_indices=geo_indices,
        construction=construction,
    )
    try:
        raw_result: object = freecad.sketch_toggle_construction(request.doc_name, request.sketch_name, geo_indices, construction)
    except Exception as exc:
        raw_result = make_sketch_toggle_construction_uncertain(
            "SKETCH_TOGGLE_CONSTRUCTION_TRANSPORT_UNCERTAIN",
            f"sketch_toggle_construction response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_toggle_construction_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run sketch_toggle_construction: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
