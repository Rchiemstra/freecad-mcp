"""Public MCP adapter for typed ``redo``."""

from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.redo_contract import (
    DocumentName,
    make_redo_uncertain,
    parse_redo_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def redo_operation(
    freecad: FreeCADConnection, doc_name: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad.redo(DocumentName(doc_name))
    except Exception as exc:
        raw_result = make_redo_uncertain(
            "REDO_TRANSPORT_UNCERTAIN",
            f"redo response unavailable: {exc}",
            committed=None,
        )
    result = parse_redo_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to redo: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
    )

