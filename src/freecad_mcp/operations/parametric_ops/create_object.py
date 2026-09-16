"""Public MCP adapter for typed ``create_object``."""

from __future__ import annotations

import json
from collections.abc import Mapping

from mcp.types import CallToolResult

from ..._shared.protocol.create_object_contract import (
    CreateObjectPayload,
    DocumentName,
    make_create_object_uncertain,
    parse_create_object_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import add_screenshot_if_available, capture_committed_screenshot, tool_fail, tool_ok


def create_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_type: str,
    obj_name: str,
    analysis_name: str | None = None,
    obj_properties: Mapping[str, object] | None = None,
) -> CallToolResult:
    payload: CreateObjectPayload = {
        "Name": obj_name,
        "Type": obj_type,
    }
    if obj_properties is not None:
        payload["Properties"] = dict(obj_properties)
    if analysis_name is not None:
        payload["Analysis"] = analysis_name
    try:
        raw_result: object = freecad.create_object(DocumentName(doc_name), payload)
    except Exception as exc:
        raw_result = make_create_object_uncertain(
            "CREATE_OBJECT_TRANSPORT_UNCERTAIN",
            f"create_object response unavailable: {exc}",
            committed=None,
        )
    # KEEP BOTH: GUI-dispatch timeout envelopes are not create_object contract
    # variants. Preserve request_id / completion_uncertain for late replay.
    if (
        isinstance(raw_result, Mapping)
        and raw_result.get("completion_uncertain") is True
        and isinstance(raw_result.get("error_code"), str)
        and raw_result.get("error_code")
    ):
        structured = dict(raw_result)
        error = raw_result.get("error")
        message = error if isinstance(error, str) and error.strip() else str(
            raw_result["error_code"]
        )
        return tool_fail(
            f"Failed to create object: {message}",
            structured=structured,
            error_code=str(raw_result["error_code"]),
        )
    result = parse_create_object_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to create object: {result['error']}",
            structured=structured,
            error_code=result["error_code"],
        )
    screenshot = capture_committed_screenshot(
        freecad, structured, only_text_feedback=only_text_feedback
    )
    ok = tool_ok(
        json.dumps(result, ensure_ascii=False, default=str),
        structured=structured,
        only_text_feedback=only_text_feedback,
    )
    return add_screenshot_if_available(ok, screenshot, only_text_feedback)
