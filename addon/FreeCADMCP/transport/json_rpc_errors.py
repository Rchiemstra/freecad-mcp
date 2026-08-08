"""Translate frozen failure results into redacted JSON-RPC 2.0 errors."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

try:
    from .._shared.protocol.redaction import redact_sensitive
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from _shared.protocol.redaction import redact_sensitive

__all__ = ["json_rpc_error_from_result"]

_APPLICATION_ERROR = -32000
_DOCUMENT_CONFLICT = -32001
_STALE_STATE = -32002
_REQUEST_CANCELLED = -32003
_LIFECYCLE_REJECTED = -32004

_CONTROL_FIELDS = frozenset(
    {"code", "error", "error_code", "message", "ok", "success"}
)
_CONFLICT_CODES = frozenset(
    {
        "DOCUMENT_CONFLICT",
        "DOCUMENT_ALREADY_OPEN",
        "DOCUMENT_LEASE_ACTIVE",
        "DOCUMENT_LEASE_CONFLICT",
        "DOCUMENT_LOCKED_BY_OTHER",
        "DOCUMENT_SELECTOR_CONFLICT",
        "FOREIGN_AUTHORITY_CHANGED",
        "LEASE_GENERATION_MISMATCH",
        "LEASE_REPLACED",
        "REQUEST_ID_REUSE",
        "REQUEST_IN_PROGRESS",
        "SAVE_AS_DESTINATION_CONFLICT",
        "SIDECAR_REPLACED",
    }
)
_STALE_CODES = frozenset(
    {
        "LEASE_OWNER_EXITED",
        "LEASE_STALE",
        "STALE_LOCK_RECOVERY_REQUIRED",
        "STALE_REVISION",
    }
)
_CANCELLATION_CODES = frozenset(
    {
        "LOCKED_ERROR_HANDOFF_CANCELLED",
        "REQUEST_CANCELLED",
        "REQUEST_CANCELLED_AFTER_MUTATION",
        "WORKER_CANCELLED",
    }
)
_LIFECYCLE_CODES = frozenset(
    {
        "DOCUMENT_CLOSE_REJECTED",
        "DOCUMENT_LIFECYCLE_REJECTED",
        "FORBIDDEN_LEASE_TRANSITION",
        "IDENTITY_REFRESH_LEASE_STATE_FORBIDS",
        "INVALID_LEASE_STATE",
        "LEASE_STATE_BLOCKS_MUTATION",
        "LEASE_STATE_BLOCKS_SAVE_PROMOTION",
        "LEASE_STATE_FORBIDS_OPERATION",
        "REQUEST_NOT_CANCELLABLE",
    }
)


def _nested_error(result: Mapping[str, Any]) -> Mapping[str, Any]:
    value = result.get("error")
    return value if isinstance(value, Mapping) else {}


def _unwrap_invoke_v2_failure(result: Mapping[str, Any]) -> Mapping[str, Any]:
    """Lift invoke_v2 inner ``result`` failures for public error extraction."""

    inner = result.get("result")
    if not isinstance(inner, Mapping):
        return result
    if inner.get("success") is not False and inner.get("ok") is not False:
        return result
    merged = dict(inner)
    for key in ("request_id", "addon_runtime_id"):
        if key in result and key not in merged:
            merged[key] = result[key]
    return merged


def _semantic_code(result: Mapping[str, Any]) -> str:
    nested = _nested_error(result)
    value = (
        result.get("code")
        or result.get("error_code")
        or nested.get("code")
        or "LEGACY_FAILURE"
    )
    return str(value)


def _application_code(semantic_code: str, details: Mapping[str, Any]) -> int:
    normalized = semantic_code.upper()
    if normalized == "LEASE_STATE_FORBIDS_OPERATION" and str(
        details.get("state") or ""
    ).upper() == "STALE":
        return _STALE_STATE
    if normalized in _CANCELLATION_CODES:
        return _REQUEST_CANCELLED
    if normalized in _STALE_CODES:
        return _STALE_STATE
    if normalized in _CONFLICT_CODES:
        return _DOCUMENT_CONFLICT
    if normalized in _LIFECYCLE_CODES:
        return _LIFECYCLE_REJECTED
    return _APPLICATION_ERROR


def _error_message(result: Mapping[str, Any]) -> str:
    if result.get("message"):
        return str(result["message"])
    nested = _nested_error(result)
    if nested.get("message"):
        return str(nested["message"])
    if isinstance(result.get("error"), str) and result.get("error"):
        return str(result["error"])
    return "RPC failed"


def _error_details(result: Mapping[str, Any]) -> dict[str, Any]:
    nested_details = _nested_error(result).get("details")
    details = dict(nested_details) if isinstance(nested_details, Mapping) else {}
    outer_details = result.get("details")
    if isinstance(outer_details, Mapping):
        for key, value in outer_details.items():
            details.setdefault(key, value)
    if result.get("state") is not None:
        details.setdefault("state", result["state"])
    return details


def _error_data(result: Mapping[str, Any], semantic_code: str) -> dict[str, Any]:
    data = _error_details(result)
    for key, value in _nested_error(result).items():
        if key not in {"code", "details", "message"}:
            data.setdefault(key, value)
    for key, value in result.items():
        if key not in _CONTROL_FIELDS:
            data.setdefault(key, value)
    data["error_code"] = semantic_code
    return redact_sensitive(data)


def json_rpc_error_from_result(result: object) -> dict[str, Any] | None:
    """Return a JSON-RPC error object for an explicit frozen failure result."""

    if not isinstance(result, Mapping):
        return None
    if result.get("ok") is not False and result.get("success") is not False:
        return None

    failure = _unwrap_invoke_v2_failure(result)
    semantic_code = _semantic_code(failure)
    details = _error_details(failure)
    return {
        "code": _application_code(semantic_code, details),
        "message": _error_message(failure),
        "data": _error_data(failure, semantic_code),
    }
