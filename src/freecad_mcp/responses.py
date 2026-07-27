import json
from collections.abc import Mapping
from typing import Any

from mcp.types import CallToolResult, ImageContent, TextContent

from .outcomes import (
    OutcomeStatus,
    extract_error_code,
    is_result_envelope,
    make_result_envelope,
    normalize_status,
    status_from_error_code,
)
from .telemetry.context import correlation_dict, get_context

ToolResponse = CallToolResult

_PROTECTED_ENVELOPE_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "operation",
        "message",
        "error",
        "error_code",
        "correlation",
        "layers",
        "data",
        "execution",
        "transaction",
        "document_health",
        "mutation_scope",
    }
)
_ERROR_STATUSES = frozenset(
    {
        OutcomeStatus.DEGRADED.value,
        OutcomeStatus.REJECTED.value,
        OutcomeStatus.FAILED.value,
        OutcomeStatus.TIMED_OUT.value,
        OutcomeStatus.CANCELLED.value,
        OutcomeStatus.UNKNOWN.value,
    }
)


def _text_item(message: str) -> TextContent:
    return TextContent(type="text", text=message)


def text_response(message: str) -> ToolResponse:
    return tool_ok(message)


def _without_images(value: Any) -> Any:
    """Copy JSON-like data without duplicating MCP image bodies."""

    if isinstance(value, Mapping):
        mime = str(value.get("mimeType") or value.get("mime_type") or "")
        result: dict[str, Any] = {}
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in {
                "image",
                "image_base64",
                "screenshot",
                "screenshots",
            }:
                continue
            if normalized == "data" and mime.startswith("image/"):
                continue
            result[str(key)] = _without_images(child)
        return result
    if isinstance(value, (list, tuple)):
        return [_without_images(child) for child in value]
    return value


def _backend_correlation(data: Mapping[str, Any] | None) -> dict[str, Any]:
    result = correlation_dict()
    if not data:
        return result
    nested = data.get("correlation")
    if isinstance(nested, Mapping):
        for key, value in nested.items():
            if value not in ("", None):
                result[str(key)] = value
    aliases = {
        "request_id": "request_id",
        "execution_id": "execution_id",
        "worker_job_id": "worker_job_id",
        "job_id": "worker_job_id",
        "document_session_uuid": "document_session_uuid",
        "recovery_incident_id": "recovery_incident_id",
    }
    execution = data.get("execution")
    for source, target in aliases.items():
        value = data.get(source)
        if value in ("", None) and isinstance(execution, Mapping):
            value = execution.get(source)
        if value not in ("", None):
            result[target] = value
    return result


def _status_for_success_data(data: Mapping[str, Any] | None) -> OutcomeStatus:
    if not data:
        return OutcomeStatus.SUCCEEDED
    explicit = data.get("outcome_status")
    if explicit is None and data.get("status") in {
        item.value for item in OutcomeStatus
    }:
        explicit = data.get("status")
    if explicit is not None:
        normalized = normalize_status(explicit, default=OutcomeStatus.SUCCEEDED)
        return OutcomeStatus(normalized)
    backend_false = data.get("success") is False or data.get("ok") is False
    if backend_false:
        code = extract_error_code(data)
        if code or data.get("error"):
            return status_from_error_code(code)
        return OutcomeStatus.CONDITION_FALSE
    health = data.get("document_health")
    if isinstance(health, Mapping):
        verdict = str(health.get("verdict") or "")
        if verdict in {"degraded", "invalid"}:
            return OutcomeStatus.DEGRADED
        if verdict == "warning":
            return OutcomeStatus.WARNING
    return OutcomeStatus.SUCCEEDED


def _envelope(
    *,
    message: str,
    structured: Mapping[str, Any] | None,
    status: OutcomeStatus | str,
    error: str | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    safe = _without_images(dict(structured or {}))
    if is_result_envelope(safe):
        result = dict(safe)
        result["correlation"] = {
            **correlation_dict(),
            **dict(result.get("correlation") or {}),
        }
        if message and not result.get("message"):
            result["message"] = message
        return result

    execution = safe.get("execution") if isinstance(safe, Mapping) else None
    transaction = safe.get("transaction") if isinstance(safe, Mapping) else None
    health = safe.get("document_health") if isinstance(safe, Mapping) else None
    mutation_scope = safe.get("mutation_scope") if isinstance(safe, Mapping) else None
    code = error_code or extract_error_code(safe)
    envelope = make_result_envelope(
        status=status,
        operation=get_context().operation or "unknown",
        message=message,
        error=error,
        error_code=code,
        correlation=_backend_correlation(safe),
        execution=execution if isinstance(execution, Mapping) else None,
        transaction=transaction if isinstance(transaction, Mapping) else None,
        document_health=health if isinstance(health, Mapping) else None,
        mutation_scope=(
            mutation_scope if isinstance(mutation_scope, Mapping) else None
        ),
        data=safe,
    )
    # Preserve legacy top-level structured fields while reserving the normalized
    # names above. Existing clients can migrate incrementally to ``data``.
    for key, value in safe.items():
        if key not in _PROTECTED_ENVELOPE_KEYS:
            envelope[key] = value
    return envelope


def json_response(
    data: object,
    *,
    status: OutcomeStatus | str | None = None,
    message: str | None = None,
) -> ToolResponse:
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
    chosen = status or _status_for_success_data(structured)
    envelope = _envelope(
        message=message or "",
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
) -> ToolResponse:
    chosen = status or _status_for_success_data(structured)
    envelope = _envelope(
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
) -> ToolResponse:
    code = error_code or extract_error_code(structured)
    chosen = status or status_from_error_code(code)
    envelope = _envelope(
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
    inner_structured = res.get("structured")
    structured: dict[str, Any] = dict(res)
    if isinstance(inner_structured, Mapping):
        structured.update(inner_structured)
    banner = _format_execution_banner(res)
    if res.get("success"):
        output = res.get("message", "")
        prefix = f"{success_prefix}\n{banner}".strip() if banner else success_prefix
        msg = f"{prefix}\n{output}".strip() if output else prefix
        # Clients render structuredContent in preference to the text block, so the
        # executed code's stdout has to travel in structured too or it is never seen.
        if output and "output" not in structured:
            structured["output"] = output
        if isinstance(res.get("execution"), dict):
            structured["execution"] = res["execution"]
        if res.get("link_warnings"):
            structured["link_warnings"] = res["link_warnings"]
        response = tool_ok(msg, structured=structured)
        if capture_view:
            return add_screenshot_if_available(response, screenshot, only_text_feedback)
        return response

    err = res.get("error") or res.get("message") or "unknown error"
    if not structured and isinstance(res.get("traceback"), dict):
        structured = dict(res["traceback"])
    body = f"{fail_prefix}: {err}"
    if banner:
        body = f"{banner}\n{body}"
    if structured:
        body += "\n" + json.dumps(structured, ensure_ascii=False, indent=2, default=str)
    fail_structured = structured
    if isinstance(res.get("execution"), dict):
        fail_structured = {**(fail_structured or {}), "execution": res["execution"]}
    return tool_fail(
        body,
        structured=fail_structured,
        error_code=extract_error_code(res),
    )
