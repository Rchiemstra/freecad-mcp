"""Public MCP adapter for typed ``undo``."""

from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.undo_contract import (
    DocumentName,
    make_undo_uncertain,
    parse_undo_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def undo_operation(
    freecad: FreeCADConnection, doc_name: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad.undo(DocumentName(doc_name))
    except Exception as exc:
        raw_result = make_undo_uncertain(
            "UNDO_TRANSPORT_UNCERTAIN",
            f"undo response unavailable: {exc}",
            committed=None,
        )
    if isinstance(raw_result, dict):
        raw_result = dict(raw_result)
        # KEEP BOTH: historical GUI success often omits document_name. Fill it
        # from the request only on verified payloads so rejections stay typed.
        if raw_result.get("success") is True:
            raw_result.setdefault("document_name", doc_name)
    result = parse_undo_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to undo: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
    )

