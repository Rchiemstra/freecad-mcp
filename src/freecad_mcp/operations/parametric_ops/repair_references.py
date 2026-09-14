"""Public MCP adapter for typed ``repair_references``."""

from __future__ import annotations

import json
from collections.abc import Mapping

from mcp.types import CallToolResult

from ..._shared.protocol.repair_references_contract import (
    DocumentName,
    make_repair_references_uncertain,
    parse_repair_references_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def repair_references_operation(
    freecad: FreeCADConnection, doc_name: str, repairs: list[Mapping[str, object]], *, recompute: bool = False, validate: bool = False,
) -> CallToolResult:
    try:
        raw_result: object = freecad.repair_references(DocumentName(doc_name), list(repairs), recompute=recompute, validate=validate)
    except Exception as exc:
        raw_result = make_repair_references_uncertain(
            "REPAIR_REFERENCES_TRANSPORT_UNCERTAIN",
            f"repair_references response unavailable: {exc}",
            committed=None,
        )
    result = parse_repair_references_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to repair references: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
    )

