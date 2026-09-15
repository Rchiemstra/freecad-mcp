from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.spreadsheet_set_alias_contract import (
    make_spreadsheet_set_alias_failure,
    make_spreadsheet_set_alias_uncertain,
    parse_spreadsheet_set_alias_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def spreadsheet_set_alias_operation(
    freecad: FreeCADConnection, only_text_feedback: bool, doc_name: str, sheet_name: str, address: str, alias: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad.spreadsheet_set_alias(doc_name, sheet_name, address, alias)
    except Exception as exc:
        raw_result = make_spreadsheet_set_alias_uncertain(
            "SPREADSHEET_SET_ALIAS_TRANSPORT_UNCERTAIN",
            f"SpreadsheetSetAlias response unavailable: {exc}",
            committed=None,
        )
    result = parse_spreadsheet_set_alias_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            "Failed to set spreadsheet alias: " + result["error"],
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
