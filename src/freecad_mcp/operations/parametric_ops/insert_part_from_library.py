"""Public MCP adapter for typed ``insert_part_from_library``."""

from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.insert_part_from_library_contract import (
    DocumentName,
    make_insert_part_from_library_uncertain,
    parse_insert_part_from_library_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import add_screenshot_if_available, tool_fail, tool_ok


def insert_part_from_library_operation(
    freecad: FreeCADConnection, only_text_feedback: bool, doc_name: str, relative_path: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad.insert_part_from_library(DocumentName(doc_name), relative_path)
    except Exception as exc:
        raw_result = make_insert_part_from_library_uncertain(
            "INSERT_PART_FROM_LIBRARY_TRANSPORT_UNCERTAIN",
            f"insert_part_from_library response unavailable: {exc}",
            committed=None,
        )
    result = parse_insert_part_from_library_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        failed = tool_fail(
            f"Failed to insert part from library: {result['error']}",
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

