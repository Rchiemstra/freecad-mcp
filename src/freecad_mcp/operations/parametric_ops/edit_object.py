"""Public MCP adapter for typed ``edit_object``."""

from __future__ import annotations

import json
from collections.abc import Mapping

from mcp.types import CallToolResult

from ..._shared.protocol.edit_object_contract import (
    DocumentName,
    ObjectName,
    make_edit_object_uncertain,
    parse_edit_object_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import add_screenshot_if_available, tool_fail, tool_ok


def edit_object_operation(
    freecad: FreeCADConnection, only_text_feedback: bool, doc_name: str, obj_name: str, obj_properties: Mapping[str, object],
) -> CallToolResult:
    try:
        raw_result: object = freecad.edit_object(DocumentName(doc_name), ObjectName(obj_name), {"Properties": dict(obj_properties)})
    except Exception as exc:
        raw_result = make_edit_object_uncertain(
            "EDIT_OBJECT_TRANSPORT_UNCERTAIN",
            f"edit_object response unavailable: {exc}",
            committed=None,
        )
    result = parse_edit_object_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        failed = tool_fail(
            f"Failed to edit object: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
        screenshot = None if only_text_feedback else freecad.get_active_screenshot()
        return add_screenshot_if_available(failed, screenshot, only_text_feedback)
    ok = tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
    screenshot = None if only_text_feedback else freecad.get_active_screenshot()
    return add_screenshot_if_available(ok, screenshot, only_text_feedback)

