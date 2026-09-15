from __future__ import annotations

import json

from mcp.types import CallToolResult

from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def list_expressions_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_name: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad.list_expressions(doc_name, object_name)
    except Exception as exc:
        return tool_fail(f"Failed to list expressions: {exc}", error_code=type(exc).__name__.upper())
    if not isinstance(raw_result, dict):
        return tool_fail("Failed to list expressions: invalid response")
    if raw_result.get("success") is False:
        return tool_fail(
            "Failed to list expressions: " + str(raw_result.get("error", "unknown")),
            structured=dict(raw_result),
            error_code=str(raw_result.get("error_code", "LIST_EXPRESSIONS_FAILED")),
        )
    return tool_ok(
        json.dumps(raw_result, ensure_ascii=False, default=str),
        structured=dict(raw_result),
        only_text_feedback=only_text_feedback,
    )
