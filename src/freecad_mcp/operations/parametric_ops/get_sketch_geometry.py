from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.get_sketch_geometry_contract import (
    make_get_sketch_geometry_uncertain,
    parse_get_sketch_geometry_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def get_sketch_geometry_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    sketch_name: str,
    include_constraints: bool = True,
    include_external: bool = False,
    global_coords: bool = False,
) -> CallToolResult:
    try:
        raw_result: object = freecad.get_sketch_geometry(
            doc_name, sketch_name, include_constraints, include_external, global_coords
        )
    except Exception as exc:
        raw_result = make_get_sketch_geometry_uncertain(
            "GET_SKETCH_GEOMETRY_TRANSPORT_UNCERTAIN",
            f"get_sketch_geometry response unavailable: {exc}",
            committed=None,
        )
    result = parse_get_sketch_geometry_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run get_sketch_geometry: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=True,
    )
