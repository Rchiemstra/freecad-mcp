from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.mirror_feature_contract import (
    make_mirror_feature_uncertain,
    parse_mirror_feature_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def mirror_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str, feature_name: str, mirror_name: str, plane: str = 'YZ_Plane', body_name: str | None = None
) -> CallToolResult:
    try:
        raw_result: object = freecad.mirror_feature(doc_name, feature_name, mirror_name, plane, body_name)
    except Exception as exc:
        raw_result = make_mirror_feature_uncertain(
            "MIRROR_FEATURE_TRANSPORT_UNCERTAIN",
            f"MirrorFeature response unavailable: {exc}",
            committed=None,
        )
    result = parse_mirror_feature_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to create mirror_feature: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
