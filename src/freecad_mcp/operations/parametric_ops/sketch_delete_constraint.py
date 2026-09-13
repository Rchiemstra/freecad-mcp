"""Typed MCP client for ``sketch_delete_constraint``."""

from __future__ import annotations

import json
from collections.abc import Sequence

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_delete_constraint_contract import (
    make_sketch_delete_constraint_uncertain,
    parse_sketch_delete_constraint_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_delete_constraint_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    constraint_indices: Sequence[int] | None = None,
    constraint_names: Sequence[str] | None = None,
) -> CallToolResult:
    try:
        raw_result: object = freecad.sketch_delete_constraint(
            doc_name,
            sketch_name,
            list(constraint_indices or []),
            list(constraint_names or []),
        )
    except Exception as exc:
        raw_result = make_sketch_delete_constraint_uncertain(
            "SKETCH_DELETE_CONSTRAINT_TRANSPORT_UNCERTAIN",
            f"Constraint delete response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_delete_constraint_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to delete sketch constraints: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
