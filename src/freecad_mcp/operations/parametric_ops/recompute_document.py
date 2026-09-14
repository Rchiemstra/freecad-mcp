"""Public MCP adapter for typed ``recompute_document``."""

from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.recompute_document_contract import (
    DocumentName,
    make_recompute_document_uncertain,
    parse_recompute_document_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def recompute_document_operation(
    freecad: FreeCADConnection, doc_name: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad.recompute_document(DocumentName(doc_name))
    except Exception as exc:
        raw_result = make_recompute_document_uncertain(
            "RECOMPUTE_DOCUMENT_TRANSPORT_UNCERTAIN",
            f"recompute_document response unavailable: {exc}",
            committed=None,
        )
    result = parse_recompute_document_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to recompute: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
    )

