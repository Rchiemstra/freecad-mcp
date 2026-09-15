from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.audit_hardcoded_dimensions_contract import (
    make_audit_hardcoded_dimensions_uncertain,
    parse_audit_hardcoded_dimensions_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def audit_hardcoded_dimensions_operation(
    freecad: FreeCADConnection,
    doc_name: str, body_name: str, flag_aliases: bool,
) -> CallToolResult:
    try:
        raw_result: object = freecad.audit_hardcoded_dimensions(doc_name, body_name, flag_aliases)
    except Exception as exc:
        raw_result = make_audit_hardcoded_dimensions_uncertain(
            "AUDIT_HARDCODED_DIMENSIONS_TRANSPORT_UNCERTAIN",
            f"audit_hardcoded_dimensions response unavailable: {exc}",
            committed=None,
        )
    result = parse_audit_hardcoded_dimensions_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to run audit_hardcoded_dimensions: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=True,
    )
