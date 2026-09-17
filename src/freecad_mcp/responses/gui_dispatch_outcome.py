"""Honest MCP outcomes for GUI dispatcher timeout and transport envelopes."""

from __future__ import annotations

from collections.abc import Mapping
from http.client import IncompleteRead, RemoteDisconnected
from typing import Any

from mcp.types import CallToolResult

from ..outcomes import OutcomeStatus
from ..outcomes_types.layer_status import LayerStatus
from .tool_results import tool_fail

GUI_TIMEOUT_ERROR_CODES = frozenset(
    {
        "GUI_TIMEOUT_BEFORE_EXECUTION",
        "GUI_TIMEOUT_DURING_EXECUTION",
        "GUI_BUSY_AFTER_TIMEOUT",
    }
)


def is_gui_dispatch_timeout_envelope(raw: object) -> bool:
    if not isinstance(raw, Mapping):
        return False
    code = str(raw.get("error_code") or "").upper()
    if code in GUI_TIMEOUT_ERROR_CODES:
        return True
    return bool(raw.get("completion_uncertain")) and "TIMEOUT" in code


def is_transport_failure_exception(exc: BaseException) -> bool:
    return isinstance(exc, (TimeoutError, RemoteDisconnected, IncompleteRead, OSError))


def tool_fail_gui_dispatch_timeout(
    raw: Mapping[str, Any],
    *,
    message_prefix: str,
) -> CallToolResult:
    structured = dict(raw)
    code = str(structured.get("error_code") or "GUI_DISPATCH_FAILED")
    before_execution = (
        code == "GUI_TIMEOUT_BEFORE_EXECUTION"
        or structured.get("timeout_stage") == "before_execution"
    )
    if before_execution:
        structured["completion_uncertain"] = False
        structured["mutation_started"] = False
        structured["retry_safe"] = True
        status = OutcomeStatus.TIMED_OUT
    else:
        structured.setdefault("completion_uncertain", True)
        structured.setdefault("retry_safe", False)
        status = (
            OutcomeStatus.TIMED_OUT
            if "TIMEOUT" in code.upper()
            else OutcomeStatus.UNKNOWN
        )

    error = structured.get("error")
    message = (
        error
        if isinstance(error, str) and error.strip()
        else f"{message_prefix}: {code}"
    )
    return tool_fail(
        message,
        structured=structured,
        error_code=code,
        status=status,
        transport_status=LayerStatus.SUCCEEDED.value,
    )


def tool_fail_transport_uncertain(
    structured: Mapping[str, Any],
    *,
    message: str,
    error_code: str,
) -> CallToolResult:
    payload = dict(structured)
    payload.setdefault("retry_safe", False)
    payload.setdefault("committed", None)
    return tool_fail(
        message,
        structured=payload,
        error_code=error_code,
        status=OutcomeStatus.UNKNOWN,
        transport_status=LayerStatus.FAILED.value,
    )
