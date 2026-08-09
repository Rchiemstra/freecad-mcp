from __future__ import annotations

import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from .constants import _SECRET_FIELD_NAMES


def _collect_secret_values(value: Any) -> set[str]:
    secrets: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).casefold()
            sensitive = (
                normalized in _SECRET_FIELD_NAMES
                or normalized.endswith("_token")
                or (
                    "fingerprint" in normalized
                    and normalized != "profile_path_fingerprint"
                )
            )
            if sensitive and isinstance(item, str) and item:
                secrets.add(item)
            else:
                secrets.update(_collect_secret_values(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            secrets.update(_collect_secret_values(item))
    return secrets


def _redact_secrets(value: Any, *, _known_secrets: set[str] | None = None) -> Any:
    """Recursively remove credential material before it reaches a widget."""

    known_secrets = (
        _collect_secret_values(value) if _known_secrets is None else _known_secrets
    )
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).casefold()
            if normalized in _SECRET_FIELD_NAMES or normalized.endswith("_token"):
                continue
            if "fingerprint" in normalized and normalized != "profile_path_fingerprint":
                continue
            redacted[str(key)] = _redact_secrets(item, _known_secrets=known_secrets)
        return redacted
    if isinstance(value, (list, tuple)):
        return [_redact_secrets(item, _known_secrets=known_secrets) for item in value]
    if isinstance(value, str):
        redacted_text = value
        for secret in known_secrets:
            redacted_text = redacted_text.replace(secret, "[redacted]")
        return redacted_text
    return value


def _timestamp_age(value: Any, *, now: float | None = None) -> float:
    """Return the non-negative age of a unix or RFC3339 timestamp."""

    current = time.time() if now is None else float(now)
    if isinstance(value, (int, float)):
        return max(0.0, current - float(value))
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return max(0.0, current - parsed.timestamp())
        except (TypeError, ValueError, OverflowError):
            pass
    return 0.0
