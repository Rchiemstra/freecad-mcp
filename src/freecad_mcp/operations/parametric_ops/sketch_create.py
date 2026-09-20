"""Typed MCP client for ``sketch_create``."""

from __future__ import annotations

import json
from collections.abc import Mapping

from mcp.types import CallToolResult

from ..._shared.protocol.sketch_create_contract import (
    make_sketch_create_uncertain,
    parse_sketch_create_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.gui_dispatch_outcome import (
    is_gui_dispatch_timeout_envelope,
    is_transport_failure_exception,
    tool_fail_gui_dispatch_timeout,
    tool_fail_transport_uncertain,
)
from ...responses.tool_results import tool_fail, tool_ok


def sketch_create_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    body_name: str | None = None,
    attach_to: str | None = None,
    attachment_offset: Mapping[str, object] | None = None,
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
        uncertain = make_sketch_create_uncertain(
            "SKETCH_CREATE_TRANSPORT_UNCERTAIN",
            f"Sketch response unavailable: {exc}",
            committed=None,
        )
        if is_transport_failure_exception(exc):
            return tool_fail_transport_uncertain(
                uncertain,
                message=f"Sketch response unavailable: {exc}",
                error_code="SKETCH_CREATE_TRANSPORT_UNCERTAIN",
            )
        raw_result = uncertain
    if is_gui_dispatch_timeout_envelope(raw_result):
        return tool_fail_gui_dispatch_timeout(
            raw_result,
            message_prefix="Failed to create sketch",
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
