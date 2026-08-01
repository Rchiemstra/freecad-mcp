"""MCP tool response builders and normalized result envelopes."""

from ..outcomes import (
    OutcomeStatus,
    extract_error_code,
    is_result_envelope,
    make_result_envelope,
    normalize_status,
    status_from_error_code,
)
from ..telemetry.context import correlation_dict, get_context
from .constants import ToolResponse
from .execute_result import from_execute_result
from .tool_results import (
    add_screenshot_if_available,
    json_response,
    text_response,
    tool_fail,
    tool_ok,
)

__all__ = [
    "OutcomeStatus",
    "ToolResponse",
    "add_screenshot_if_available",
    "correlation_dict",
    "extract_error_code",
    "from_execute_result",
    "get_context",
    "is_result_envelope",
    "json_response",
    "make_result_envelope",
    "normalize_status",
    "status_from_error_code",
    "text_response",
    "tool_fail",
    "tool_ok",
]
