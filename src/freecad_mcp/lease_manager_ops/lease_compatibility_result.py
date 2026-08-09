"""Immutable, redacted copy of diagnostics returned by a legacy lease path."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

_AUTHORITY_FIELD_NAMES = frozenset(
    {
        "auth",
        "authentication",
        "authorization",
        "bearer",
        "capabilities",
        "capability",
        "credential",
        "credentials",
        "grant",
        "grants",
        "lease_credential",
        "lease_credentials",
        "lease_token",
        "password",
        "proof",
        "secret",
        "session_token",
        "signature",
        "token",
    }
)
_AUTHORITY_FIELD_SUFFIXES = (
    "_authentication",
    "_authorization",
    "_bearer",
    "_capabilities",
    "_capability",
    "_credential",
    "_credentials",
    "_grant",
    "_grants",
    "_password",
    "_proof",
    "_secret",
    "_signature",
    "_token",
)
_DIAGNOSTIC_FIELD_SUFFIXES = (
    "_available",
    "_count",
    "_status",
    "_supported",
)
_FROZEN_PUBLIC_CAPABILITY_FIELDS = frozenset({"rpc_method_capabilities"})
_AUTHORITY_FIELD_SEGMENTS = frozenset(
    {
        "auth",
        "authentication",
        "authorization",
        "bearer",
        "capabilities",
        "capability",
        "credential",
        "credentials",
        "grant",
        "grants",
        "password",
        "proof",
        "secret",
        "signature",
        "token",
    }
)
_AUTHORITY_COMPACT_MARKERS = (
    "authentication",
    "authorisation",
    "authorization",
    "authorities",
    "authority",
    "authoris",
    "authoriz",
    "bearer",
    "capability",
    "credential",
    "grant",
    "password",
    "permission",
    "privilege",
    "proof",
    "secret",
    "signature",
    "token",
)
_PUBLIC_DIAGNOSTIC_STATES = frozenset(
    {
        "absent",
        "active",
        "available",
        "disabled",
        "enabled",
        "error",
        "expired",
        "inactive",
        "invalid",
        "ok",
        "present",
        "stale",
        "supported",
        "unknown",
        "unavailable",
        "unsupported",
        "unverified",
        "valid",
        "verified",
    }
)
_ASSIGNMENT_LABEL = re.compile(
    r"(?:[\"'](?P<quoted>[^\"']+)[\"']|"
    r"(?P<bare>[^,;{}\[\]\r\n:=\"']+?))\s*[:=]"
)
_BEARER_MARKER = re.compile(r"(?i)\bbearer\s+")


def _normalized_field_name(key: str) -> str:
    acronym_split = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", key)
    snake_case = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", acronym_split)
    return re.sub(r"[^a-z0-9]+", "_", snake_case.lower()).strip("_")


def _is_safe_authority_diagnostic(normalized: str, value: Any) -> bool:
    if normalized.endswith("_count"):
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0
    if normalized.endswith(("_available", "_supported")) and isinstance(value, bool):
        return True
    return (
        normalized.endswith("_status")
        and isinstance(value, str)
        and value.lower() in _PUBLIC_DIAGNOSTIC_STATES
    )


def _is_authority_field(key: str, value: Any) -> bool:
    normalized = _normalized_field_name(key)
    if normalized in _FROZEN_PUBLIC_CAPABILITY_FIELDS:
        return False
    compact = normalized.replace("_", "")
    authority_named = (
        normalized in _AUTHORITY_FIELD_NAMES
        or normalized.endswith(_AUTHORITY_FIELD_SUFFIXES)
        or bool(set(normalized.split("_")) & _AUTHORITY_FIELD_SEGMENTS)
        or any(marker in compact for marker in _AUTHORITY_COMPACT_MARKERS)
        or (
            (compact.startswith("auth") and not compact.startswith("author"))
            or compact.endswith("auth")
        )
    )
    if not authority_named:
        return False
    return not (
        normalized.endswith(_DIAGNOSTIC_FIELD_SUFFIXES)
        and _is_safe_authority_diagnostic(normalized, value)
    )


def _redact_text(value: str) -> str:
    if _BEARER_MARKER.search(value):
        return "[REDACTED]"
    if any(
        _is_authority_field(
            (match.group("quoted") or match.group("bare")).strip(),
            "unsafe",
        )
        for match in _ASSIGNMENT_LABEL.finditer(value)
    ):
        return "[REDACTED]"
    return value


def _sanitize_scalar(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_text(value)
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("compatibility result contains a non-finite number")
        return value
    raise TypeError("compatibility result contains non-JSON diagnostic data")


def _sanitize_public_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("compatibility results require string diagnostic keys")
            safe_key = _redact_text(key)
            if _is_authority_field(safe_key, child):
                raise ValueError(
                    "compatibility result contains non-public authority data"
                )
            if safe_key in sanitized:
                raise ValueError(
                    "compatibility result contains ambiguous diagnostic keys"
                )
            sanitized[safe_key] = _sanitize_public_value(child)
        return sanitized
    elif isinstance(value, (list, tuple)):
        return [_sanitize_public_value(child) for child in value]
    return _sanitize_scalar(value)


@dataclass(frozen=True, slots=True, repr=False)
class LeaseCompatibilityResult:
    """Hold copied public diagnostics without authority or mutation behavior.

    Generation, owner, and heartbeat-status metadata remain valid diagnostics.
    Credential- or authority-bearing fields are rejected, and textual inline
    credential fragments are redacted before the private copy is retained.
    """

    _payload_json: str = field(init=False, repr=False)

    def __init__(self, payload: Mapping[str, Any]) -> None:
        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")
        sanitized = _sanitize_public_value(payload)
        object.__setattr__(
            self,
            "_payload_json",
            json.dumps(
                sanitized,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a fresh defensive copy of the redacted public diagnostics."""

        result = json.loads(self._payload_json)
        assert isinstance(result, dict)
        return result

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted>)"
