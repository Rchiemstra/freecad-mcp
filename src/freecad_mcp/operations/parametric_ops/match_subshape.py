from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.match_subshape_contract import (
    make_match_subshape_uncertain,
    parse_match_subshape_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def match_subshape_operation(
    freecad: FreeCADConnection,
    doc_name: str, source_object: str, source_subshape: str, target_object: str, limit: int, tolerance: float,
) -> CallToolResult:
    try:
        raw_result: object = freecad.match_subshape(doc_name, source_object, source_subshape, target_object, limit, tolerance)
    except Exception as exc:
        raw_result = make_match_subshape_uncertain(
            "MATCH_SUBSHAPE_TRANSPORT_UNCERTAIN",
            f"match_subshape response unavailable: {exc}",
            committed=None,
        )
    result = parse_match_subshape_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run match_subshape: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=True,
    )
