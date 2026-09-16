from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.validate_geometry_contract import (
    make_validate_geometry_uncertain,
    parse_validate_geometry_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def validate_geometry_operation(
    freecad: FreeCADConnection,
    doc_name: str, obj_name: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad.validate_geometry(doc_name, obj_name)
    except Exception as exc:
        raw_result = make_validate_geometry_uncertain(
            "VALIDATE_GEOMETRY_TRANSPORT_UNCERTAIN",
            f"validate_geometry response unavailable: {exc}",
            committed=None,
        )
    result = parse_validate_geometry_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run validate_geometry: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=True,
    )
