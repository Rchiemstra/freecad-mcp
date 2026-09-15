from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.face_normal_contract import (
    make_face_normal_uncertain,
    parse_face_normal_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def face_normal_operation(
    freecad: FreeCADConnection,
    doc_name: str, object_name: str, face: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad.face_normal(doc_name, object_name, face)
    except Exception as exc:
        raw_result = make_face_normal_uncertain(
            "FACE_NORMAL_TRANSPORT_UNCERTAIN",
            f"face_normal response unavailable: {exc}",
            committed=None,
        )
    result = parse_face_normal_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run face_normal: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=True,
    )
