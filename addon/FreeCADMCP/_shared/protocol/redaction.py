"""Sensitive-value redaction helpers for lease protocol diagnostics."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from .constants import _REDACTED, _SENSITIVE_KEYS


def _key_is_sensitive(key: object) -> bool:
    normalized = str(key).lower().replace("-", "_")
    if normalized in _SENSITIVE_KEYS:
        return True
    return (
        normalized.endswith("_token")
        or normalized.endswith("_secret")
        or normalized.endswith("_token_digest")
        or normalized.endswith("_token_fingerprint")
        or normalized.endswith("_secret_fingerprint")
    )


def redact_sensitive(value: Any) -> Any:
    """Deep-copy JSON-like data while replacing credential-bearing values."""

    if isinstance(value, Mapping):
        return {
            str(key): _REDACTED if _key_is_sensitive(key) else redact_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_sensitive(item) for item in value]
    return copy.deepcopy(value)
