from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.spreadsheet_create_contract import (
    make_spreadsheet_create_failure,
    make_spreadsheet_create_uncertain,
    parse_spreadsheet_create_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def spreadsheet_create_operation(
    freecad: FreeCADConnection, only_text_feedback: bool, doc_name: str, sheet_name: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad._invoke_mutation_v2(
            "spreadsheet_create",
            {
            "doc_name": doc_name,
            "sheet_name": sheet_name,
            },
            document_names=(doc_name,),
            operation_name="Create spreadsheet",
        )
        if raw_result is None:
            raw_result = make_spreadsheet_create_uncertain(
                "SPREADSHEET_CREATE_TRANSPORT_UNCERTAIN",
                "spreadsheet_create response unavailable: JSON-RPC session is not connected",
                committed=None,
            )
    except Exception as exc:
        raw_result = make_spreadsheet_create_uncertain(
            "SPREADSHEET_CREATE_TRANSPORT_UNCERTAIN",
            f"SpreadsheetCreate response unavailable: {exc}",
            committed=None,
        )
    result = parse_spreadsheet_create_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            "Failed to create spreadsheet: " + result["error"],
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
