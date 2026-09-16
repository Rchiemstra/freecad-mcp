from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.bounding_box_contract import (
    BoundingBoxRequest,
    make_bounding_box_uncertain,
    parse_bounding_box_response,
    DocumentName,
    ObjectName,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def bounding_box_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    obj_name: str,
) -> CallToolResult:
    request = BoundingBoxRequest(
        doc_name=DocumentName(doc_name),
        obj_name=ObjectName(obj_name)
    )
    try:
        raw_result: object = freecad.bounding_box(doc_name, obj_name)
    except Exception as exc:
        raw_result = make_bounding_box_uncertain(
            "BOUNDING_BOX_TRANSPORT_UNCERTAIN",
            f"BoundingBox response unavailable: {exc}",
            committed=None,
        )
    result = parse_bounding_box_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run bounding_box: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=True,
    )
