"""Helpers for bounding replay-cache response payloads."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from .constants import _REDACTED


def scrub_exact_secrets(value: Any, secrets: Sequence[str]) -> Any:
    normalized = tuple(secret for secret in (str(item) for item in secrets) if secret)
    if isinstance(value, Mapping):
        return {
            str(key): scrub_exact_secrets(item, normalized)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [scrub_exact_secrets(item, normalized) for item in value]
    if isinstance(value, str):
        result = value
        for secret in normalized:
            result = result.replace(secret, _REDACTED)
        return result
    return copy.deepcopy(value)


def completion_tombstone(request_id: str) -> dict[str, Any]:
    return {
        "ok": False,
        "request_id": request_id,
        "error": {
            "code": "REQUEST_ALREADY_COMPLETED",
            "message": (
                "The matching authenticated request already completed; "
                "its retained result is no longer available"
            ),
        },
    }


def is_completion_tombstone(response: Any) -> bool:
    return bool(
        isinstance(response, Mapping)
        and isinstance(response.get("error"), Mapping)
        and response["error"].get("code") == "REQUEST_ALREADY_COMPLETED"
    )
