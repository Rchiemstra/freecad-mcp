from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_add_external_projection_contract import (
    make_sketch_add_external_projection_failure,
    make_sketch_add_external_projection_uncertain,
    parse_sketch_add_external_projection_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_add_external_projection_operation(
    freecad: FreeCADConnection, only_text_feedback: bool, doc_name: str, sketch_name: str, source_ref: str, projection_mode: str = "auto", defining: bool = False, allow_gui_geometry_loop: bool = False,
) -> CallToolResult:
    if projection_mode not in {"auto", "edge", "face", "point"}:
        failure = make_sketch_add_external_projection_failure("INVALID_ARGUMENT", "projection_mode must be one of: auto, edge, face, point")
        return tool_fail(failure["error"], structured=dict(failure), error_code=failure["error_code"])
    if not allow_gui_geometry_loop:
        failure = make_sketch_add_external_projection_failure(
            "gui_geometry_loop_opt_in_required",
            "sketch_add_external_projection requires allow_gui_geometry_loop=true",
        )
        return tool_fail(failure["error"], structured=dict(failure), error_code=failure["error_code"])
    try:
        raw_result: object = freecad._invoke_mutation_v2(
            "sketch_add_external_projection",
            {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "source_ref": source_ref,
            "projection_mode": projection_mode,
            "defining": defining,
            "allow_gui_geometry_loop": allow_gui_geometry_loop,
            },
            document_names=(doc_name,),
            operation_name="Add external projection",
        )
        if raw_result is None:
            raw_result = make_sketch_add_external_projection_uncertain(
                "SKETCH_ADD_EXTERNAL_PROJECTION_TRANSPORT_UNCERTAIN",
                "sketch_add_external_projection response unavailable: JSON-RPC session is not connected",
                committed=None,
            )
    except Exception as exc:
        raw_result = make_sketch_add_external_projection_uncertain(
            "SKETCH_ADD_EXTERNAL_PROJECTION_TRANSPORT_UNCERTAIN",
            f"SketchAddExternalProjection response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_add_external_projection_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            "Failed to add external projection: " + result["error"],
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
