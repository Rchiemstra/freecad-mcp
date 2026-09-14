from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_import_points_contract import (
    SketchImportPointsRequest,
    DocumentName,
    SketchName,
    make_sketch_import_points_uncertain,
    parse_sketch_import_points_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_import_points_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    points: list[dict[str, float]],
    construction: bool = False,
) -> CallToolResult:
    request = SketchImportPointsRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        points=points,
        construction=construction,
    )
    try:
        raw_result: object = freecad.sketch_import_points(request.doc_name, request.sketch_name, points, construction)
    except Exception as exc:
        raw_result = make_sketch_import_points_uncertain(
            "SKETCH_IMPORT_POINTS_TRANSPORT_UNCERTAIN",
            f"sketch_import_points response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_import_points_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run sketch_import_points: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
