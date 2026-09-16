"""Public MCP adapter for typed ``create_document``."""

from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.create_document_contract import (
    DocumentName,
    make_create_document_uncertain,
    parse_create_document_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def create_document_operation(
    freecad: FreeCADConnection, name: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad.create_document(DocumentName(name))
    except Exception as exc:
        raw_result = make_create_document_uncertain(
            "CREATE_DOCUMENT_TRANSPORT_UNCERTAIN",
            f"create_document response unavailable: {exc}",
            committed=None,
        )
    result = parse_create_document_response(raw_result)
    structured = dict(result)
    # Historic add-ons could still return an acquisition credential.
    # It is a deprecated wire artifact: MCP neither stores nor
    # acknowledges it, and it must never cross the public tool result.
    if "credential" in structured:
        structured.pop("credential", None)
        structured["credential_stored"] = False
        structured["token_exported"] = False
    if result["success"] is False:
        return tool_fail(
            f"Failed to create document: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
    )

