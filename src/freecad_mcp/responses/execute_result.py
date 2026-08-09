import json
from collections.abc import Mapping
from typing import Any

from ..outcomes import extract_error_code
from .tool_results import add_screenshot_if_available, tool_fail, tool_ok


def format_execution_banner(res: dict[str, Any]) -> str:
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


def _merge_execute_structured(res: dict[str, Any]) -> dict[str, Any]:
    inner_structured = res.get("structured")
    structured: dict[str, Any] = dict(res)
    if isinstance(inner_structured, Mapping):
        structured.update(inner_structured)
    return structured


def _augment_success_structured(structured: dict[str, Any], res: dict[str, Any]) -> None:
    output = res.get("message", "")
    if output and "output" not in structured:
        structured["output"] = output
    if isinstance(res.get("execution"), dict):
        structured["execution"] = res["execution"]
    if res.get("link_warnings"):
        structured["link_warnings"] = res["link_warnings"]


def _success_execute_message(res: dict[str, Any], success_prefix: str, banner: str) -> str:
    output = res.get("message", "")
    prefix = f"{success_prefix}\n{banner}".strip() if banner else success_prefix
    return f"{prefix}\n{output}".strip() if output else prefix


def _failure_execute_body(
    res: dict[str, Any],
    fail_prefix: str,
    banner: str,
    structured: dict[str, Any],
) -> str:
    err = res.get("error") or res.get("message") or "unknown error"
    body = f"{fail_prefix}: {err}"
    if banner:
        body = f"{banner}\n{body}"
    if structured:
        body += "\n" + json.dumps(structured, ensure_ascii=False, indent=2, default=str)
    return body


def _failure_execute_structured(
    res: dict[str, Any],
    structured: dict[str, Any],
) -> dict[str, Any] | None:
    fail_structured = structured
    if not fail_structured and isinstance(res.get("traceback"), dict):
        fail_structured = dict(res["traceback"])
    if isinstance(res.get("execution"), dict):
        fail_structured = {**(fail_structured or {}), "execution": res["execution"]}
    return fail_structured


def from_execute_result(
    res: dict[str, Any],
    *,
    success_prefix: str,
    fail_prefix: str,
    screenshot: str | None = None,
    only_text_feedback: bool = False,
    capture_view: bool = True,
):
    """Build a CallToolResult from a FreeCAD RPC execute_code response."""
    structured = _merge_execute_structured(res)
    banner = format_execution_banner(res)
    if res.get("success"):
        _augment_success_structured(structured, res)
        msg = _success_execute_message(res, success_prefix, banner)
        response = tool_ok(msg, structured=structured)
        if capture_view:
            return add_screenshot_if_available(response, screenshot, only_text_feedback)
        return response

    fail_structured = _failure_execute_structured(res, structured)
    body = _failure_execute_body(res, fail_prefix, banner, fail_structured or {})
    return tool_fail(
        body,
        structured=fail_structured,
        error_code=extract_error_code(res),
    )
