"""Typed MCP client for ``pad_feature``."""

from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.pad_feature_contract import (
    make_pad_feature_failure,
    make_pad_feature_uncertain,
    parse_pad_feature_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.gui_dispatch_outcome import (
    is_gui_dispatch_timeout_envelope,
    is_transport_failure_exception,
    tool_fail_gui_dispatch_timeout,
    tool_fail_transport_uncertain,
)
from ...responses.tool_results import (
    add_screenshot_if_available,
    capture_committed_screenshot,
    tool_fail,
    tool_ok,
)


def pad_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    pad_name: str,
    length: float,
    body_name: str | None = None,
    symmetric: bool = False,
    reversed_dir: bool = False,
    strict: bool = False,
) -> CallToolResult:
    if strict and not body_name:
        failure = make_pad_feature_failure(
            "INVALID_ARGUMENT",
            "strict PartDesign mode requires an explicit body_name",
        )
        return tool_fail(
            f"Failed to create pad: {failure['error']}",
            structured=dict(failure),
            error_code=failure["error_code"],
        )
    try:
        raw_result: object = freecad.pad_feature(
            doc_name, sketch_name, pad_name, length, body_name, symmetric, reversed_dir
        )
    except Exception as exc:
        uncertain = make_pad_feature_uncertain(
            "PAD_FEATURE_TRANSPORT_UNCERTAIN",
            f"Pad response unavailable: {exc}",
            committed=None,
        )
        if is_transport_failure_exception(exc):
            return tool_fail_transport_uncertain(
                uncertain,
                message=f"Pad response unavailable: {exc}",
                error_code="PAD_FEATURE_TRANSPORT_UNCERTAIN",
            )
        raw_result = uncertain
    if is_gui_dispatch_timeout_envelope(raw_result):
        return tool_fail_gui_dispatch_timeout(
            raw_result,
            message_prefix="Failed to create pad",
        )
    result = parse_pad_feature_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to create pad: {result['error']}",
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
