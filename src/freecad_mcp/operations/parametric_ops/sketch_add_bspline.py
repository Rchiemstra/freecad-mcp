from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_add_bspline_contract import (
    SketchAddBsplineRequest,
    DocumentName,
    SketchName,
    make_sketch_add_bspline_uncertain,
    parse_sketch_add_bspline_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_add_bspline_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    poles: list[dict[str, float]],
    degree: int = 3,
    weights: list[float] | None = None,
    knots: list[float] | None = None,
    multiplicities: list[int] | None = None,
    periodic: bool = False,
    construction: bool = False,
) -> CallToolResult:
    request = SketchAddBsplineRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        poles=poles,
        degree=degree,
        weights=weights,
        knots=knots,
        multiplicities=multiplicities,
        periodic=periodic,
        construction=construction,
    )
    try:
        raw_result: object = freecad.sketch_add_bspline(request.doc_name, request.sketch_name, poles, degree, weights, knots, multiplicities, periodic, construction)
    except Exception as exc:
        raw_result = make_sketch_add_bspline_uncertain(
            "SKETCH_ADD_BSPLINE_TRANSPORT_UNCERTAIN",
            f"sketch_add_bspline response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_add_bspline_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run sketch_add_bspline: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
