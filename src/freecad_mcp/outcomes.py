"""Stable MCP result statuses and normalized envelope helpers."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any

RESULT_SCHEMA_VERSION = 1


class OutcomeStatus(StrEnum):
    SUCCEEDED = "succeeded"
    CONDITION_FALSE = "condition_false"
    WARNING = "warning"
    DEGRADED = "degraded"
    REJECTED = "rejected"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class LayerStatus(StrEnum):
    SUCCEEDED = "succeeded"
    CONDITION_FALSE = "condition_false"
    WARNING = "warning"
    DEGRADED = "degraded"
    REJECTED = "rejected"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


NORMALIZED_STATUSES = frozenset(item.value for item in OutcomeStatus)
LAYER_NAMES = (
    "transport_status",
    "tool_status",
    "backend_status",
    "transaction_status",
    "document_health_status",
)


COMMON_ERROR_CODES = frozenset(
    {
        "AUTHENTICATION_FAILED",
        "BACKEND_FAILURE",
        "CANCELLED",
        "CONDITION_FALSE",
        "GUI_BUSY_AFTER_TIMEOUT",
        "GUI_COMPLETION_UNCERTAIN",
        "GUI_DISPATCH_FAILED",
        "GUI_TASK_FAILED",
        "GUI_TIMEOUT_BEFORE_EXECUTION",
        "GUI_TIMEOUT_DURING_EXECUTION",
        "INVALID_ARGUMENT",
        "MALFORMED_RESPONSE",
        "POLICY_REJECTED",
        "RPC_INVOCATION_FAILED",
        "TRANSACTION_ROLLBACK_FAILED",
        "WORKER_CANCELLED",
        "WORKER_CANCEL_REQUESTED",
        "WORKER_TASK_FAILED",
        "WORKER_TERMINATION_FAILED",
        "WORKER_TIMEOUT_BEFORE_EXECUTION",
        "WORKER_TIMEOUT_DURING_EXECUTION",
    }
)


def normalize_status(value: Any, *, default: OutcomeStatus) -> str:
    rendered = str(getattr(value, "value", value) or "")
    return rendered if rendered in NORMALIZED_STATUSES else default.value


def status_from_error_code(error_code: str | None) -> OutcomeStatus:
    code = str(error_code or "").upper()
    if "TIMEOUT" in code:
        return OutcomeStatus.TIMED_OUT
    if "CANCEL" in code:
        return OutcomeStatus.CANCELLED
    if any(
        token in code
        for token in (
            "REJECT",
            "FORBIDDEN",
            "POLICY",
            "LEASE_",
            "LOCK",
            "SCOPE",
            "UNSAFE",
            "NOT_ALLOWED",
            "DISABLED",
        )
    ):
        return OutcomeStatus.REJECTED
    if "DEGRADED" in code or "HEALTH" in code or "ROLLBACK" in code:
        return OutcomeStatus.DEGRADED
    return OutcomeStatus.FAILED


def extract_error_code(value: Any) -> str | None:
    """Return a backend error code without replacing subsystem-specific codes."""

    if isinstance(value, Mapping):
        direct = value.get("error_code") or value.get("code")
        if direct:
            return str(direct)
        nested = value.get("error")
        if isinstance(nested, Mapping):
            code = nested.get("code") or nested.get("error_code")
            if code:
                return str(code)
        for key in ("result", "structured", "data"):
            nested_code = extract_error_code(value.get(key))
            if nested_code:
                return nested_code
    code = getattr(value, "code", None)
    return str(code) if code else None


def is_result_envelope(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and value.get("schema_version") == RESULT_SCHEMA_VERSION
        and value.get("status") in NORMALIZED_STATUSES
        and isinstance(value.get("operation"), str)
    )


def _copy_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def make_result_envelope(
    *,
    status: OutcomeStatus | str = OutcomeStatus.SUCCEEDED,
    operation: str = "unknown",
    message: str = "",
    error: str | None = None,
    error_code: str | None = None,
    correlation: Mapping[str, Any] | None = None,
    execution: Mapping[str, Any] | None = None,
    transaction: Mapping[str, Any] | None = None,
    document_health: Mapping[str, Any] | None = None,
    mutation_scope: Mapping[str, Any] | None = None,
    layers: Mapping[str, Any] | None = None,
    data: Any = None,
) -> dict[str, Any]:
    normalized = normalize_status(status, default=OutcomeStatus.UNKNOWN)
    envelope: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": normalized,
        "operation": str(operation or "unknown"),
        "message": str(message or ""),
        "error": None if error is None else str(error),
        "error_code": None if error_code is None else str(error_code),
        "correlation": _copy_mapping(correlation),
        "data": {} if data is None else data,
    }
    for name, value in (
        ("execution", execution),
        ("transaction", transaction),
        ("document_health", document_health),
        ("mutation_scope", mutation_scope),
    ):
        if isinstance(value, Mapping):
            envelope[name] = dict(value)
    layer_values = dict(layers or {})
    layer_values.setdefault("transport_status", LayerStatus.SUCCEEDED.value)
    layer_values.setdefault("tool_status", normalized)
    layer_values.setdefault(
        "backend_status",
        LayerStatus.SUCCEEDED.value
        if normalized
        in {
            OutcomeStatus.SUCCEEDED.value,
            OutcomeStatus.CONDITION_FALSE.value,
            OutcomeStatus.WARNING.value,
        }
        else normalized,
    )
    layer_values.setdefault(
        "transaction_status",
        (
            str(envelope["transaction"].get("status") or LayerStatus.UNKNOWN.value)
            if "transaction" in envelope
            else LayerStatus.NOT_APPLICABLE.value
        ),
    )
    layer_values.setdefault(
        "document_health_status",
        (
            str(envelope["document_health"].get("verdict") or LayerStatus.UNKNOWN.value)
            if "document_health" in envelope
            else LayerStatus.NOT_APPLICABLE.value
        ),
    )
    envelope["layers"] = layer_values
    return envelope


__all__ = [
    "COMMON_ERROR_CODES",
    "LAYER_NAMES",
    "NORMALIZED_STATUSES",
    "RESULT_SCHEMA_VERSION",
    "LayerStatus",
    "OutcomeStatus",
    "extract_error_code",
    "is_result_envelope",
    "make_result_envelope",
    "normalize_status",
    "status_from_error_code",
]
