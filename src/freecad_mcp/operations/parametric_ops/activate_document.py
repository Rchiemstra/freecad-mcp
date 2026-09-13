"""Public MCP adapter for typed ``activate_document``."""

from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.activate_document_contract import (
    DocumentName,
    make_activate_document_uncertain,
    parse_activate_document_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def activate_document_operation(
    freecad: FreeCADConnection, doc_name: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad.activate_document(DocumentName(doc_name))
    except Exception as exc:
        raw_result = make_activate_document_uncertain(
            "ACTIVATE_DOCUMENT_TRANSPORT_UNCERTAIN",
            f"activate_document response unavailable: {exc}",
            committed=None,
        )
    result = parse_activate_document_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to activate document: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
    )

