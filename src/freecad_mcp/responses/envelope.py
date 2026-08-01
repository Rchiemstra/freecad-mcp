from collections.abc import Mapping
from typing import Any

from ..outcomes import (
    OutcomeStatus,
    extract_error_code,
    is_result_envelope,
    make_result_envelope,
)
from ..telemetry.context import correlation_dict, get_context
from .constants import _PROTECTED_ENVELOPE_KEYS
from .envelope_helpers import backend_correlation, status_for_success_data, without_images


def build_envelope(
    *,
    message: str,
    structured: Mapping[str, Any] | None,
    status: OutcomeStatus | str,
    error: str | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    safe = without_images(dict(structured or {}))
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
        correlation=backend_correlation(safe),
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


__all__ = ["build_envelope", "status_for_success_data"]
