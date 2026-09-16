from __future__ import annotations

import json

from mcp.types import CallToolResult

from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def get_sketch_diagnostics_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    sketch_name: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad.get_sketch_diagnostics(doc_name, sketch_name)
    except Exception as exc:
        return tool_fail(f"Failed to get sketch diagnostics: {exc}", error_code=type(exc).__name__.upper())
    if not isinstance(raw_result, dict):
        return tool_fail("Failed to get sketch diagnostics: invalid response")
    if raw_result.get("success") is False:
        return tool_fail(
            "Failed to get sketch diagnostics: " + str(raw_result.get("error", "unknown")),
            structured=dict(raw_result),
            error_code=str(raw_result.get("error_code", "GET_SKETCH_DIAGNOSTICS_FAILED")),
        )
    return tool_ok(
        json.dumps(raw_result, ensure_ascii=False, default=str),
        structured=dict(raw_result),
        only_text_feedback=True,
    )
