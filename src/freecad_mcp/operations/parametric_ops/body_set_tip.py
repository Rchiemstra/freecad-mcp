from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.body_set_tip_contract import (
    BodyName,
    BodySetTipRequest,
    DocumentName,
    FeatureName,
    make_body_set_tip_uncertain,
    parse_body_set_tip_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def body_set_tip_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    body_name: str,
    feature_name: str,
) -> CallToolResult:
    request = BodySetTipRequest(
        doc_name=DocumentName(doc_name),
        body_name=BodyName(body_name),
        feature_name=FeatureName(feature_name),
    )
    try:
        raw_result: object = freecad.body_set_tip(
            request.doc_name, request.body_name, request.feature_name
        )
    except Exception as exc:
        raw_result = make_body_set_tip_uncertain(
            "BODY_SET_TIP_TRANSPORT_UNCERTAIN",
            f"Body Tip response unavailable: {exc}",
            committed=None,
        )
    result = parse_body_set_tip_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to set body tip: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
