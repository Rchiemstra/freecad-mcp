from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.capture_state_contract import (
    make_capture_state_failure,
    make_capture_state_uncertain,
    parse_capture_state_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import tool_fail, tool_ok


def capture_state_operation(
    freecad: FreeCADConnection, only_text_feedback: bool, doc_name: str, object_names: object = None,
) -> CallToolResult:
    try:
        raw_result: object = freecad.capture_state(doc_name, object_names)
    except Exception as exc:
        raw_result = make_capture_state_uncertain(
            "CAPTURE_STATE_TRANSPORT_UNCERTAIN",
            f"CaptureState response unavailable: {exc}",
            committed=None,
        )
    result = parse_capture_state_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            "Failed to capture state: " + result["error"],
            structured=structured,
            error_code=result["error_code"],
        )
    return tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
