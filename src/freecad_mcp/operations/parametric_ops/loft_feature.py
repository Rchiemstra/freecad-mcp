from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.loft_feature_contract import (
    make_loft_feature_uncertain,
    parse_loft_feature_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def loft_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str, sketch_names: list[str], loft_name: str, body_name: str | None = None, ruled: bool = False, closed: bool = False
) -> CallToolResult:
    try:
        raw_result: object = freecad.loft_feature(doc_name, sketch_names, loft_name, body_name, ruled, closed)
    except Exception as exc:
        raw_result = make_loft_feature_uncertain(
            "LOFT_FEATURE_TRANSPORT_UNCERTAIN",
            f"LoftFeature response unavailable: {exc}",
            committed=None,
        )
    result = parse_loft_feature_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to create loft_feature: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
