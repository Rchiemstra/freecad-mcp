from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.polar_pattern_feature_contract import (
    make_polar_pattern_feature_uncertain,
    parse_polar_pattern_feature_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def polar_pattern_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str, feature_name: str, pattern_name: str, occurrences: int, angle: float = 360.0, axis: str = 'Z_Axis', body_name: str | None = None, reversed_dir: bool = False
) -> CallToolResult:
    try:
        raw_result: object = freecad.polar_pattern_feature(doc_name, feature_name, pattern_name, occurrences, angle, axis, body_name, reversed_dir)
    except Exception as exc:
        raw_result = make_polar_pattern_feature_uncertain(
            "POLAR_PATTERN_FEATURE_TRANSPORT_UNCERTAIN",
            f"PolarPatternFeature response unavailable: {exc}",
            committed=None,
        )
    result = parse_polar_pattern_feature_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to create polar_pattern_feature: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
