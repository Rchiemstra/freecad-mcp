"""Public MCP adapter for typed ``close_document``."""

from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.close_document_contract import (
    DocumentName,
    make_close_document_uncertain,
    parse_close_document_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def close_document_operation(
    freecad: FreeCADConnection, doc_name: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad.close_document(DocumentName(doc_name))
    except Exception as exc:
        raw_result = make_close_document_uncertain(
            "CLOSE_DOCUMENT_TRANSPORT_UNCERTAIN",
            f"close_document response unavailable: {exc}",
            committed=None,
        )
    result = parse_close_document_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to close document: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
    )

