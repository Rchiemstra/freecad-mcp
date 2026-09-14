"""Public MCP adapter for typed ``recompute_and_wait``."""

from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.recompute_and_wait_contract import (
    DocumentName,
    make_recompute_and_wait_uncertain,
    parse_recompute_and_wait_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def recompute_and_wait_operation(
    freecad: FreeCADConnection, doc_name: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad.recompute_and_wait(DocumentName(doc_name))
    except Exception as exc:
        raw_result = make_recompute_and_wait_uncertain(
            "RECOMPUTE_AND_WAIT_TRANSPORT_UNCERTAIN",
            f"recompute_and_wait response unavailable: {exc}",
            committed=None,
        )
    result = parse_recompute_and_wait_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to recompute and wait: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
    )

