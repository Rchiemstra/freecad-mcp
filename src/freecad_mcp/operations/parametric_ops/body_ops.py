from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.body_create_contract import (
    BodyCreateRequest,
    BodyName,
    DocumentName,
    make_body_create_uncertain,
    parse_body_create_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok
from .body_set_tip import body_set_tip_operation as body_set_tip_operation


def body_create_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    body_name: str,
) -> CallToolResult:
    request = BodyCreateRequest(
        doc_name=DocumentName(doc_name),
        body_name=BodyName(body_name),
    )
    try:
        raw_result: object = freecad.body_create(request.doc_name, request.body_name)
    except Exception as exc:
        raw_result = make_body_create_uncertain(
            "BODY_CREATE_TRANSPORT_UNCERTAIN",
            f"Body response unavailable: {exc}",
            committed=None,
        )
    result = parse_body_create_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to create body: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
