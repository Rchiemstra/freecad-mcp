from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.set_expression_contract import (
    make_set_expression_uncertain,
    parse_set_expression_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.gui_dispatch_outcome import (
    is_gui_dispatch_timeout_envelope,
    is_transport_failure_exception,
    tool_fail_gui_dispatch_timeout,
    tool_fail_transport_uncertain,
)
from ...responses.tool_results import tool_fail, tool_ok


def set_expression_operation(
    freecad: FreeCADConnection, only_text_feedback: bool, doc_name: str, object_name: str, prop_path: str, expression: str,
) -> CallToolResult:
    try:
        raw_result: object = freecad.set_expression(doc_name, object_name, prop_path, expression)
    except Exception as exc:
        uncertain = make_set_expression_uncertain(
            "SET_EXPRESSION_TRANSPORT_UNCERTAIN",
            f"SetExpression response unavailable: {exc}",
            committed=None,
        )
        if is_transport_failure_exception(exc):
            return tool_fail_transport_uncertain(
                uncertain,
                message=f"SetExpression response unavailable: {exc}",
                error_code="SET_EXPRESSION_TRANSPORT_UNCERTAIN",
            )
        raw_result = uncertain
    if is_gui_dispatch_timeout_envelope(raw_result):
        return tool_fail_gui_dispatch_timeout(
            raw_result,
            message_prefix="Failed to set expression",
        )
    result = parse_set_expression_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            "Failed to set expression: " + result["error"],
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
