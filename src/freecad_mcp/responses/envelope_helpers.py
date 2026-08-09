from collections.abc import Mapping
from typing import Any

from ..outcomes import (
    OutcomeStatus,
    extract_error_code,
    normalize_status,
    status_from_error_code,
)
from ..telemetry.context import correlation_dict


def without_images(value: Any) -> Any:
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
            result[str(key)] = without_images(child)
        return result
    if isinstance(value, (list, tuple)):
        return [without_images(child) for child in value]
    return value


def backend_correlation(data: Mapping[str, Any] | None) -> dict[str, Any]:
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


def status_for_success_data(data: Mapping[str, Any] | None) -> OutcomeStatus:
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
