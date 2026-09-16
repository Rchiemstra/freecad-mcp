from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.spreadsheet_get_cells_contract import (
    make_spreadsheet_get_cells_failure,
    make_spreadsheet_get_cells_uncertain,
    parse_spreadsheet_get_cells_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def spreadsheet_get_cells_operation(
    freecad: FreeCADConnection, only_text_feedback: bool, doc_name: str, sheet_name: str, addresses: object,
) -> CallToolResult:
    try:
        raw_result: object = freecad.spreadsheet_get_cells(doc_name, sheet_name, addresses)
    except Exception as exc:
        raw_result = make_spreadsheet_get_cells_uncertain(
            "SPREADSHEET_GET_CELLS_TRANSPORT_UNCERTAIN",
            f"SpreadsheetGetCells response unavailable: {exc}",
            committed=None,
        )
    result = parse_spreadsheet_get_cells_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            "Failed to get spreadsheet cells: " + result["error"],
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
