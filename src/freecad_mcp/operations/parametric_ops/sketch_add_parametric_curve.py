from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_add_parametric_curve_contract import (
    SketchAddParametricCurveRequest,
    DocumentName,
    SketchName,
    make_sketch_add_parametric_curve_failure,
    make_sketch_add_parametric_curve_uncertain,
    parse_sketch_add_parametric_curve_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_add_parametric_curve_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    x_expr: str,
    y_expr: str,
    t_start: float,
    t_end: float,
    samples: int = 100,
    construction: bool = False,
) -> CallToolResult:
    if samples < 10 or samples > 2000:
        failure = make_sketch_add_parametric_curve_failure(
            "INVALID_ARGUMENT",
            "samples must be between 10 and 2000",
        )
        return tool_fail(
            f"Failed to run sketch_add_parametric_curve: {failure['error']}",
            structured=dict(failure),
            error_code=failure["error_code"],
        )
    if t_start >= t_end:
        failure = make_sketch_add_parametric_curve_failure(
            "INVALID_ARGUMENT",
            "t_start must be less than t_end",
        )
        return tool_fail(
            f"Failed to run sketch_add_parametric_curve: {failure['error']}",
            structured=dict(failure),
            error_code=failure["error_code"],
        )
    request = SketchAddParametricCurveRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        x_expr=x_expr,
        y_expr=y_expr,
        t_start=t_start,
        t_end=t_end,
        samples=samples,
        construction=construction,
    )
    try:
        raw_result: object = freecad.sketch_add_parametric_curve(request.doc_name, request.sketch_name, x_expr, y_expr, t_start, t_end, samples, construction)
    except Exception as exc:
        raw_result = make_sketch_add_parametric_curve_uncertain(
            "SKETCH_ADD_PARAMETRIC_CURVE_TRANSPORT_UNCERTAIN",
            f"sketch_add_parametric_curve response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_add_parametric_curve_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run sketch_add_parametric_curve: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
