import json
from typing import Any

from mcp.types import CallToolResult, ImageContent, TextContent

ToolResponse = CallToolResult


def _text_item(message: str) -> TextContent:
    return TextContent(type="text", text=message)


def text_response(message: str) -> ToolResponse:
    return tool_ok(message)


def json_response(data: object) -> ToolResponse:
    return tool_ok(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def tool_ok(
    message: str,
    *,
    screenshot: str | None = None,
    only_text_feedback: bool = False,
    structured: dict[str, Any] | None = None,
) -> ToolResponse:
    content: list[TextContent | ImageContent] = [_text_item(message)]
    if screenshot and not only_text_feedback:
        content.append(ImageContent(type="image", data=screenshot, mimeType="image/png"))
    return CallToolResult(content=content, structuredContent=structured, isError=False)


def tool_fail(
    message: str,
    *,
    structured: dict[str, Any] | None = None,
) -> ToolResponse:
    return CallToolResult(
        content=[_text_item(message)],
        structuredContent=structured,
        isError=True,
    )


def add_screenshot_if_available(
    response: ToolResponse,
    screenshot: str | None,
    only_text_feedback: bool,
) -> ToolResponse:
    if only_text_feedback or screenshot is None or response.isError:
        return response
    content = list(response.content)
    content.append(ImageContent(type="image", data=screenshot, mimeType="image/png"))
    return CallToolResult(
        content=content,
        structuredContent=response.structuredContent,
        isError=response.isError,
    )


def from_execute_result(
    res: dict[str, Any],
    *,
    success_prefix: str,
    fail_prefix: str,
    screenshot: str | None = None,
    only_text_feedback: bool = False,
    capture_view: bool = True,
) -> ToolResponse:
    """Build a CallToolResult from a FreeCAD RPC execute_code response."""
    structured = res.get("structured")
    if res.get("success"):
        output = res.get("message", "")
        msg = f"{success_prefix}\n{output}".strip() if output else success_prefix
        response = tool_ok(msg, structured=structured)
        if capture_view:
            return add_screenshot_if_available(response, screenshot, only_text_feedback)
        return response

    err = res.get("error") or res.get("message") or "unknown error"
    if structured is None and isinstance(res.get("traceback"), dict):
        structured = res["traceback"]
    body = f"{fail_prefix}: {err}"
    if structured:
        body += "\n" + json.dumps(structured, ensure_ascii=False, indent=2, default=str)
    return tool_fail(body, structured=structured if isinstance(structured, dict) else None)
