from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.clear_expression_contract import (
    make_clear_expression_failure,
    make_clear_expression_uncertain,
    parse_clear_expression_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def clear_expression_operation(
    freecad: FreeCADConnection, only_text_feedback: bool, doc_name: str, object_name: str, prop_path: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad._invoke_mutation_v2(
            "clear_expression",
            {
            "doc_name": doc_name,
            "object_name": object_name,
            "prop_path": prop_path,
            },
            document_names=(doc_name,),
            operation_name="Clear expression",
        )
        if raw_result is None:
            raw_result = make_clear_expression_uncertain(
                "CLEAR_EXPRESSION_TRANSPORT_UNCERTAIN",
                "clear_expression response unavailable: JSON-RPC session is not connected",
                committed=None,
            )
    except Exception as exc:
        raw_result = make_clear_expression_uncertain(
            "CLEAR_EXPRESSION_TRANSPORT_UNCERTAIN",
            f"ClearExpression response unavailable: {exc}",
            committed=None,
        )
    result = parse_clear_expression_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            "Failed to clear expression: " + result["error"],
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
