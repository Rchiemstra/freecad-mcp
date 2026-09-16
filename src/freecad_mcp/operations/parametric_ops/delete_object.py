"""Public MCP adapter for typed ``delete_object``."""

from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.delete_object_contract import (
    DocumentName,
    ObjectName,
    make_delete_object_uncertain,
    parse_delete_object_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import add_screenshot_if_available, capture_committed_screenshot, tool_fail, tool_ok


def delete_object_operation(
    freecad: FreeCADConnection, only_text_feedback: bool, doc_name: str, obj_name: str, recursive: bool = False, force: bool = False,
) -> CallToolResult:
    try:
        raw_result: object = freecad.delete_object(DocumentName(doc_name), ObjectName(obj_name), recursive=recursive, force=force)
    except Exception as exc:
        raw_result = make_delete_object_uncertain(
            "DELETE_OBJECT_TRANSPORT_UNCERTAIN",
            f"delete_object response unavailable: {exc}",
            committed=None,
        )
    result = parse_delete_object_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to delete object: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    screenshot = capture_committed_screenshot(
        freecad, structured, only_text_feedback=only_text_feedback
    )
    ok = tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
    return add_screenshot_if_available(ok, screenshot, only_text_feedback)

