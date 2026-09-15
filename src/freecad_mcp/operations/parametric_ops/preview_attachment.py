from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.preview_attachment_contract import (
    make_preview_attachment_failure,
    make_preview_attachment_uncertain,
    parse_preview_attachment_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def preview_attachment_operation(
    freecad: FreeCADConnection, only_text_feedback: bool, doc_name: str, datum_name: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad.preview_attachment(doc_name, datum_name)
    except Exception as exc:
        raw_result = make_preview_attachment_uncertain(
            "PREVIEW_ATTACHMENT_TRANSPORT_UNCERTAIN",
            f"PreviewAttachment response unavailable: {exc}",
            committed=None,
        )
    result = parse_preview_attachment_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            "Failed to preview attachment: " + result["error"],
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
