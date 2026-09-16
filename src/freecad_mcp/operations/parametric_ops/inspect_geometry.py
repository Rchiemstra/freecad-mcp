from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.inspect_geometry_contract import (
    make_inspect_geometry_uncertain,
    parse_inspect_geometry_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def inspect_geometry_operation(
    freecad: FreeCADConnection,
    doc_name: str, object_name: str, subshape: str | None,
) -> CallToolResult:
    try:
        raw_result: object = freecad.inspect_geometry(doc_name, object_name, subshape)
    except Exception as exc:
        raw_result = make_inspect_geometry_uncertain(
            "INSPECT_GEOMETRY_TRANSPORT_UNCERTAIN",
            f"inspect_geometry response unavailable: {exc}",
            committed=None,
        )
    result = parse_inspect_geometry_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run inspect_geometry: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=True,
    )
