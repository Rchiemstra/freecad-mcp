import json
from collections.abc import Mapping
from typing import Any

from mcp.types import CallToolResult, ImageContent, TextContent

from ..outcomes import OutcomeStatus, extract_error_code, status_from_error_code
from .constants import _ERROR_STATUSES
from .envelope import build_envelope, status_for_success_data


def _text_item(message: str) -> TextContent:
    return TextContent(type="text", text=message)


def text_response(message: str) -> CallToolResult:
    return tool_ok(message)


def json_response(
    data: object,
    *,
    status: OutcomeStatus | str | None = None,
    message: str | None = None,
) -> CallToolResult:
    readable = (
        message
        if message is not None
        # Keep the compatibility text as one complete JSON line. Several
        # existing clients intentionally scan mixed FreeCAD output from the end
        # for the last JSON object, while structuredContent remains the
        # authoritative machine representation.
        else json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    )
    structured = data if isinstance(data, Mapping) else {"value": data}
    chosen = status or status_for_success_data(structured)
    envelope = build_envelope(
        message=readable if message is None else message,
        structured=structured,
        status=chosen,
    )
    return tool_ok(readable, structured=envelope)


def tool_ok(
    message: str,
    *,
    screenshot: str | None = None,
    screenshots: list[str] | None = None,
    only_text_feedback: bool = False,
    structured: dict[str, Any] | None = None,
    status: OutcomeStatus | str | None = None,
) -> CallToolResult:
    chosen = status or status_for_success_data(structured)
    envelope = build_envelope(
        message=message,
        structured=structured,
        status=chosen,
    )
    content: list[TextContent | ImageContent] = [_text_item(message)]
    if not only_text_feedback:
        images = list(screenshots or [])
        if screenshot:
            images.insert(0, screenshot)
        for image in images:
            if image:
                content.append(ImageContent(type="image", data=image, mimeType="image/png"))
    return CallToolResult(
        content=content,
        structuredContent=envelope,
        isError=str(envelope["status"]) in _ERROR_STATUSES,
    )


def tool_fail(
    message: str,
    *,
    structured: dict[str, Any] | None = None,
    error_code: str | None = None,
    status: OutcomeStatus | str | None = None,
) -> CallToolResult:
    code = error_code or extract_error_code(structured)
    chosen = status or status_from_error_code(code)
    envelope = build_envelope(
        message=message,
        structured=structured,
        status=chosen,
        error=message,
        error_code=code,
    )
    return CallToolResult(
        content=[_text_item(message)],
        structuredContent=envelope,
        isError=str(envelope["status"]) in _ERROR_STATUSES,
    )


def add_screenshot_if_available(
    response: CallToolResult,
    screenshot: str | None,
    only_text_feedback: bool,
) -> CallToolResult:
    if only_text_feedback or screenshot is None or response.isError:
        return response
    content = list(response.content)
    content.append(ImageContent(type="image", data=screenshot, mimeType="image/png"))
    return CallToolResult(
        content=content,
        structuredContent=response.structuredContent,
        isError=response.isError,
    )
