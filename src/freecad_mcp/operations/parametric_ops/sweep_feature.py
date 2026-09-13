from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.sweep_feature_contract import (
    make_sweep_feature_uncertain,
    parse_sweep_feature_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sweep_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str, profile_sketch: str, path_sketch: str, sweep_name: str, body_name: str | None = None, frenet: bool = False
) -> CallToolResult:
    try:
        raw_result: object = freecad.sweep_feature(doc_name, profile_sketch, path_sketch, sweep_name, body_name, frenet)
    except Exception as exc:
        raw_result = make_sweep_feature_uncertain(
            "SWEEP_FEATURE_TRANSPORT_UNCERTAIN",
            f"SweepFeature response unavailable: {exc}",
            committed=None,
        )
    result = parse_sweep_feature_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to create sweep_feature: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
