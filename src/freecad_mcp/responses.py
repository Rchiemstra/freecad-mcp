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
    screenshots: list[str] | None = None,
    only_text_feedback: bool = False,
    structured: dict[str, Any] | None = None,
) -> ToolResponse:
    content: list[TextContent | ImageContent] = [_text_item(message)]
    if not only_text_feedback:
        images = list(screenshots or [])
        if screenshot:
            images.insert(0, screenshot)
        for image in images:
            if image:
                content.append(ImageContent(type="image", data=image, mimeType="image/png"))
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


def _format_execution_banner(res: dict[str, Any]) -> str:
    """Human-readable line showing whether GUI or worker ran the code."""
    execution = res.get("execution")
    if not isinstance(execution, dict):
        return ""
    mode = execution.get("mode") or "unknown"
    if mode == "worker":
        parts = ["[execution: worker"]
        job_id = execution.get("job_id")
        if job_id:
            parts.append(f"job={job_id}")
        duration = execution.get("duration_ms")
        if isinstance(duration, (int, float)):
            parts.append(f"{duration:.0f}ms")
        snap = execution.get("snapshot_duration_ms")
        if isinstance(snap, (int, float)) and snap > 0:
            parts.append(f"snapshot={snap:.0f}ms")
        if res.get("link_warnings"):
            parts.append(f"link_warnings={len(res['link_warnings'])}")
        return " ".join(parts) + "]"
    if mode == "gui":
        return "[execution: gui]"
    return f"[execution: {mode}]"


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
    banner = _format_execution_banner(res)
    if res.get("success"):
        output = res.get("message", "")
        prefix = f"{success_prefix}\n{banner}".strip() if banner else success_prefix
        msg = f"{prefix}\n{output}".strip() if output else prefix
        # Clients render structuredContent in preference to the text block, so the
        # executed code's stdout has to travel in structured too or it is never seen.
        if not isinstance(structured, dict):
            structured = {}
        else:
            structured = dict(structured)
        if output and "output" not in structured:
            structured["output"] = output
        if isinstance(res.get("execution"), dict):
            structured["execution"] = res["execution"]
        if res.get("link_warnings"):
            structured["link_warnings"] = res["link_warnings"]
        response = tool_ok(msg, structured=structured or None)
        if capture_view:
            return add_screenshot_if_available(response, screenshot, only_text_feedback)
        return response

    err = res.get("error") or res.get("message") or "unknown error"
    if structured is None and isinstance(res.get("traceback"), dict):
        structured = res["traceback"]
    body = f"{fail_prefix}: {err}"
    if banner:
        body = f"{banner}\n{body}"
    if structured:
        body += "\n" + json.dumps(structured, ensure_ascii=False, indent=2, default=str)
    fail_structured = structured if isinstance(structured, dict) else None
    if isinstance(res.get("execution"), dict):
        fail_structured = {**(fail_structured or {}), "execution": res["execution"]}
    return tool_fail(body, structured=fail_structured)
