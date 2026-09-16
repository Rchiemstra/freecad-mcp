"""Typed MCP client for ``pocket_feature``."""

from __future__ import annotations

import json

from mcp.types import CallToolResult

from ..._shared.protocol.pocket_feature_contract import (
    make_pocket_feature_failure,
    make_pocket_feature_uncertain,
    parse_pocket_feature_response,
)
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import add_screenshot_if_available, capture_committed_screenshot, tool_fail, tool_ok


def pocket_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    pocket_name: str,
    length: float,
    body_name: str | None = None,
    symmetric: bool = False,
    reversed_dir: bool = False,
    strict: bool = False,
) -> CallToolResult:
    if strict and not body_name:
        failure = make_pocket_feature_failure(
            "INVALID_ARGUMENT",
            "strict PartDesign mode requires an explicit body_name",
        )
        return tool_fail(
            f"Failed to create pocket: {failure['error']}",
            structured=dict(failure),
            error_code=failure["error_code"],
        )
    try:
        raw_result: object = freecad.pocket_feature(
            doc_name, sketch_name, pocket_name, length, body_name, symmetric, reversed_dir
        )
    except Exception as exc:
        raw_result = make_pocket_feature_uncertain(
            "POCKET_FEATURE_TRANSPORT_UNCERTAIN",
            f"Pocket response unavailable: {exc}",
            committed=None,
        )
    result = parse_pocket_feature_response(raw_result)
    structured = dict(result)
    if result["success"] is False:
        return tool_fail(
            f"Failed to create pocket: {result['error']}",
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
