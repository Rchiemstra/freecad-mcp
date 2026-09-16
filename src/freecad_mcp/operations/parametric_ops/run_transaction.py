from __future__ import annotations

import json

from mcp.types import CallToolResult

from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def run_transaction_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    label: str,
    code: str,
    dry_run: bool = False,
    commit_on_success: bool = True,
) -> CallToolResult:
    try:
        raw_result: object = freecad.run_transaction(
            doc_name, label, code, dry_run, commit_on_success
        )
    except Exception as exc:
        return tool_fail(f"Failed to run transaction: {exc}", error_code=type(exc).__name__.upper())
    if not isinstance(raw_result, dict):
        return tool_fail("Failed to run transaction: invalid response")
    if raw_result.get("success") is False:
        return tool_fail(
            "Failed to run transaction: " + str(raw_result.get("error", "unknown")),
            structured=dict(raw_result),
            error_code=str(raw_result.get("error_code", "RUN_TRANSACTION_FAILED")),
        )
    return tool_ok(
        json.dumps(raw_result, ensure_ascii=False, default=str),
        structured=dict(raw_result),
        only_text_feedback=only_text_feedback,
    )
