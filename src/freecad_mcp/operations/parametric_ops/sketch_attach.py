"""Typed MCP client for ``sketch_attach``."""

from __future__ import annotations

import json
from collections.abc import Mapping

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_attach_contract import (
    make_sketch_attach_uncertain,
    parse_sketch_attach_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def sketch_attach_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    support: str | Mapping[str, object],
    attachment_offset: Mapping[str, object] | None = None,
) -> CallToolResult:
    try:
        if attachment_offset is None:
            raw_result: object = freecad.sketch_attach(doc_name, sketch_name, support)
        else:
            raw_result = freecad.sketch_attach(
                doc_name, sketch_name, support, attachment_offset
            )
    except Exception as exc:
        raw_result = make_sketch_attach_uncertain(
            "SKETCH_ATTACH_TRANSPORT_UNCERTAIN",
            f"Sketch attach response unavailable: {exc}",
            committed=None,
        )
    result = parse_sketch_attach_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to attach sketch: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
