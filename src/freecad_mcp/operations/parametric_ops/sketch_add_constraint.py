"""Typed MCP client for ``sketch_add_constraint``."""

from __future__ import annotations

import json
from collections.abc import Sequence

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_add_constraint_contract import (
    make_sketch_add_constraint_uncertain,
    parse_sketch_add_constraint_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.gui_dispatch_outcome import (
    is_gui_dispatch_timeout_envelope,
    is_transport_failure_exception,
    tool_fail_gui_dispatch_timeout,
    tool_fail_transport_uncertain,
)
from ...responses.tool_results import tool_fail, tool_ok


def sketch_add_constraint_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    constraints: Sequence[object],
) -> CallToolResult:
    try:
        raw_result: object = freecad.sketch_add_constraint(
            doc_name, sketch_name, list(constraints)
        )
    except Exception as exc:
        uncertain = make_sketch_add_constraint_uncertain(
            "SKETCH_ADD_CONSTRAINT_TRANSPORT_UNCERTAIN",
            f"Constraint response unavailable: {exc}",
            committed=None,
        )
        if is_transport_failure_exception(exc):
            return tool_fail_transport_uncertain(
                uncertain,
                message=f"Constraint response unavailable: {exc}",
                error_code="SKETCH_ADD_CONSTRAINT_TRANSPORT_UNCERTAIN",
            )
        raw_result = uncertain
    if is_gui_dispatch_timeout_envelope(raw_result):
        return tool_fail_gui_dispatch_timeout(
            raw_result,
            message_prefix="Failed to add constraints",
        )
    result = parse_sketch_add_constraint_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to add constraints: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
