from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.spreadsheet_set_cells_contract import (
    make_spreadsheet_set_cells_failure,
    make_spreadsheet_set_cells_uncertain,
    parse_spreadsheet_set_cells_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.gui_dispatch_outcome import (
    gui_dispatch_timeout_envelope_from_exception,
    is_gui_dispatch_timeout_envelope,
    is_transport_failure_exception,
    tool_fail_gui_dispatch_timeout,
    tool_fail_transport_uncertain,
)
from ...responses.tool_results import tool_fail, tool_ok


def spreadsheet_set_cells_operation(
    freecad: FreeCADConnection, only_text_feedback: bool, doc_name: str, sheet_name: str, cells: object,
) -> CallToolResult:
    if not isinstance(cells, list) or not cells:
        invalid = make_spreadsheet_set_cells_failure("INVALID_ARGUMENT", "cells must be a non-empty list")
        return tool_fail(invalid["error"], structured=dict(invalid), error_code=invalid["error_code"])
    try:
        raw_result: object = freecad.spreadsheet_set_cells(doc_name, sheet_name, cells)
    except Exception as exc:
        timeout_envelope = gui_dispatch_timeout_envelope_from_exception(exc)
        if timeout_envelope is not None:
            return tool_fail_gui_dispatch_timeout(
                timeout_envelope,
                message_prefix="Failed to set spreadsheet cells",
            )
        uncertain = make_spreadsheet_set_cells_uncertain(
            "SPREADSHEET_SET_CELLS_TRANSPORT_UNCERTAIN",
            f"SpreadsheetSetCells response unavailable: {exc}",
            committed=None,
        )
        if is_transport_failure_exception(exc):
            return tool_fail_transport_uncertain(
                uncertain,
                message=f"SpreadsheetSetCells response unavailable: {exc}",
                error_code="SPREADSHEET_SET_CELLS_TRANSPORT_UNCERTAIN",
            )
        raw_result = uncertain
    if is_gui_dispatch_timeout_envelope(raw_result):
        return tool_fail_gui_dispatch_timeout(
            raw_result,
            message_prefix="Failed to set spreadsheet cells",
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
