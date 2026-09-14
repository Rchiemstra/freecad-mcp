from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.spreadsheet_set_cells_contract import (
    make_spreadsheet_set_cells_failure,
    make_spreadsheet_set_cells_uncertain,
    parse_spreadsheet_set_cells_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def spreadsheet_set_cells_operation(
    freecad: FreeCADConnection, only_text_feedback: bool, doc_name: str, sheet_name: str, cells: object,
) -> CallToolResult:
    if not isinstance(cells, list) or not cells:
        invalid = make_spreadsheet_set_cells_failure("INVALID_ARGUMENT", "cells must be a non-empty list")
        return tool_fail(invalid["error"], structured=dict(invalid), error_code=invalid["error_code"])
    try:
        raw_result: object = freecad._invoke_mutation_v2(
            "spreadsheet_set_cells",
            {
            "doc_name": doc_name,
            "sheet_name": sheet_name,
            "cells": cells,
            },
            document_names=(doc_name,),
            operation_name="Set spreadsheet cells",
        )
        if raw_result is None:
            raw_result = make_spreadsheet_set_cells_uncertain(
                "SPREADSHEET_SET_CELLS_TRANSPORT_UNCERTAIN",
                "spreadsheet_set_cells response unavailable: JSON-RPC session is not connected",
                committed=None,
            )
    except Exception as exc:
        raw_result = make_spreadsheet_set_cells_uncertain(
            "SPREADSHEET_SET_CELLS_TRANSPORT_UNCERTAIN",
            f"SpreadsheetSetCells response unavailable: {exc}",
            committed=None,
        )
    result = parse_spreadsheet_set_cells_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            "Failed to set spreadsheet cells: " + result["error"],
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
