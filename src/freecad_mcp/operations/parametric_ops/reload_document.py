"""Public MCP adapter for typed ``reload_document``."""

from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.reload_document_contract import (
    DocumentName,
    make_reload_document_uncertain,
    parse_reload_document_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def reload_document_operation(
    freecad: FreeCADConnection, doc_name: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad.reload_document(DocumentName(doc_name))
    except Exception as exc:
        raw_result = make_reload_document_uncertain(
            "RELOAD_DOCUMENT_TRANSPORT_UNCERTAIN",
            f"reload_document response unavailable: {exc}",
            committed=None,
        )
    result = parse_reload_document_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to reload document: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
    )

