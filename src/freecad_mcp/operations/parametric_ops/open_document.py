"""Public MCP adapter for typed ``open_document``."""

from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.open_document_contract import (
    PathName,
    make_open_document_uncertain,
    parse_open_document_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def open_document_operation(
    freecad: FreeCADConnection, path: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad.open_document(PathName(path))
    except Exception as exc:
        raw_result = make_open_document_uncertain(
            "OPEN_DOCUMENT_TRANSPORT_UNCERTAIN",
            f"open_document response unavailable: {exc}",
            committed=None,
        )
    result = parse_open_document_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to open document: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
    )

