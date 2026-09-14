from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.translate_contract import (
    TranslateRequest,
    make_translate_uncertain,
    parse_translate_response,
    DocumentName,
    ObjectName,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def translate_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    dx: float,
    dy: float,
    dz: float,
) -> CallToolResult:
    request = TranslateRequest(
        doc_name=DocumentName(doc_name),
        obj_name=ObjectName(obj_name),
        dx=dx,
        dy=dy,
        dz=dz
    )
    try:
        raw_result: object = freecad.translate(doc_name, obj_name, dx, dy, dz)
    except Exception as exc:
        raw_result = make_translate_uncertain(
            "TRANSLATE_TRANSPORT_UNCERTAIN",
            f"Translate response unavailable: {exc}",
            committed=None,
        )
    result = parse_translate_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run translate: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
