from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.helical_sweep_feature_contract import (
    make_helical_sweep_feature_uncertain,
    parse_helical_sweep_feature_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def helical_sweep_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str, profile_sketch: str, helix_name: str, pitch: float, height: float, radius: float, body_name: str | None = None, left_handed: bool = False, reversed_dir: bool = False
) -> CallToolResult:
    try:
        raw_result: object = freecad.helical_sweep_feature(doc_name, profile_sketch, helix_name, pitch, height, radius, body_name, left_handed, reversed_dir)
    except Exception as exc:
        raw_result = make_helical_sweep_feature_uncertain(
            "HELICAL_SWEEP_FEATURE_TRANSPORT_UNCERTAIN",
            f"HelicalSweepFeature response unavailable: {exc}",
            committed=None,
        )
    result = parse_helical_sweep_feature_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to create helical_sweep_feature: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
