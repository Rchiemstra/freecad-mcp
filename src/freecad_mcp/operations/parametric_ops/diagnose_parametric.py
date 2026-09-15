from __future__ import annotations

import json

from mcp.types import CallToolResult

from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def diagnose_parametric_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_name: str | None = None,
) -> CallToolResult:
    try:
        raw_result: object = freecad.diagnose_parametric(doc_name, object_name)
    except Exception as exc:
        return tool_fail(f"Failed to diagnose parametric model: {exc}", error_code=type(exc).__name__.upper())
    if not isinstance(raw_result, dict):
        return tool_fail("Failed to diagnose parametric model: invalid response")
    if raw_result.get("success") is False:
        return tool_fail(
            "Failed to diagnose parametric model: " + str(raw_result.get("error", "unknown")),
            structured=dict(raw_result),
            error_code=str(raw_result.get("error_code", "DIAGNOSE_PARAMETRIC_FAILED")),
        )
    return tool_ok(
        json.dumps(raw_result, ensure_ascii=False, default=str),
        structured=dict(raw_result),
        only_text_feedback=only_text_feedback,
    )
