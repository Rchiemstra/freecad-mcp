from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.fillet_feature_contract import (
    make_fillet_feature_uncertain,
    parse_fillet_feature_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def fillet_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str, base_feature: str, fillet_name: str, radius: float, edge_refs: list[str] | None = None, body_name: str | None = None
) -> CallToolResult:
    try:
        raw_result: object = freecad.fillet_feature(doc_name, base_feature, fillet_name, radius, edge_refs, body_name)
    except Exception as exc:
        raw_result = make_fillet_feature_uncertain(
            "FILLET_FEATURE_TRANSPORT_UNCERTAIN",
            f"FilletFeature response unavailable: {exc}",
            committed=None,
        )
    result = parse_fillet_feature_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to create fillet_feature: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
