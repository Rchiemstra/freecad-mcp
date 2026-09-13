"""Typed MCP client for ``sketch_edit_constraint``."""

from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_edit_constraint_contract import (
    make_sketch_edit_constraint_failure,
    make_sketch_edit_constraint_uncertain,
    parse_sketch_edit_constraint_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_edit_constraint_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    value: float | None = None,
    name: str | None = None,
    index: int | None = None,
) -> CallToolResult:
    if name is None and index is None:
        failure = make_sketch_edit_constraint_failure(
            "INVALID_ARGUMENT",
            "Provide constraint name or index",
        )
        return tool_fail(
            f"Failed to edit constraint: {failure['error']}",
            structured=dict(failure),
            error_code=failure["error_code"],
        )
    try:
        raw_result: object = freecad.sketch_edit_constraint(
            doc_name, sketch_name, value, name, index
        )
    except Exception as exc:
        raw_result = make_sketch_edit_constraint_uncertain(
            "SKETCH_EDIT_CONSTRAINT_TRANSPORT_UNCERTAIN",
            f"Constraint edit response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_edit_constraint_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to edit constraint: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
