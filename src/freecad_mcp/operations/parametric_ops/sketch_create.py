"""Typed MCP client for ``sketch_create``."""

from __future__ import annotations

import json

from typing import Any

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_create_contract import (
    make_sketch_create_uncertain,
    parse_sketch_create_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_create_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    body_name: str | None = None,
    attach_to: str | None = None,
    attachment_offset: dict[str, Any] | None = None,
) -> CallToolResult:
    try:
        if attachment_offset is None:
            raw_result: object = freecad.sketch_create(
                doc_name, sketch_name, body_name, attach_to
            )
        else:
            raw_result = freecad.sketch_create(
                doc_name, sketch_name, body_name, attach_to, attachment_offset
            )
    except Exception as exc:
        raw_result = make_sketch_create_uncertain(
            "SKETCH_CREATE_TRANSPORT_UNCERTAIN",
            f"Sketch response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_create_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to create sketch: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
