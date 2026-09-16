from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_symmetry_contract import (
    SketchSymmetryRequest,
    DocumentName,
    SketchName,
    make_sketch_symmetry_uncertain,
    parse_sketch_symmetry_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_symmetry_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    geo_indices: list[int],
    symmetry_geo: int,
    copy: bool = True,
) -> CallToolResult:
    request = SketchSymmetryRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        geo_indices=tuple(geo_indices),
        symmetry_geo=symmetry_geo,
        copy=copy,
    )
    try:
        raw_result: object = freecad.sketch_symmetry(request.doc_name, request.sketch_name, geo_indices, symmetry_geo, copy)
    except Exception as exc:
        raw_result = make_sketch_symmetry_uncertain(
            "SKETCH_SYMMETRY_TRANSPORT_UNCERTAIN",
            f"sketch_symmetry response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_symmetry_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run sketch_symmetry: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
