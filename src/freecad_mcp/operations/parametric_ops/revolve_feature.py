from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.revolve_feature_contract import (
    make_revolve_feature_uncertain,
    parse_revolve_feature_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def revolve_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str, sketch_name: str, revolve_name: str, angle: float = 360.0, axis: str = 'Z_Axis', body_name: str | None = None, symmetric: bool = False, reversed_dir: bool = False
) -> CallToolResult:
    try:
        raw_result: object = freecad.revolve_feature(doc_name, sketch_name, revolve_name, angle, axis, body_name, symmetric, reversed_dir)
    except Exception as exc:
        raw_result = make_revolve_feature_uncertain(
            "REVOLVE_FEATURE_TRANSPORT_UNCERTAIN",
            f"RevolveFeature response unavailable: {exc}",
            committed=None,
        )
    result = parse_revolve_feature_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to create revolve_feature: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
