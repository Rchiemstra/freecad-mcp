from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.chamfer_feature_contract import (
    make_chamfer_feature_uncertain,
    parse_chamfer_feature_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def chamfer_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str, base_feature: str, chamfer_name: str, size: float, edge_refs: list[str] | None = None, body_name: str | None = None
) -> CallToolResult:
    try:
        raw_result: object = freecad.chamfer_feature(doc_name, base_feature, chamfer_name, size, edge_refs, body_name)
    except Exception as exc:
        raw_result = make_chamfer_feature_uncertain(
            "CHAMFER_FEATURE_TRANSPORT_UNCERTAIN",
            f"ChamferFeature response unavailable: {exc}",
            committed=None,
        )
    result = parse_chamfer_feature_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to create chamfer_feature: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
