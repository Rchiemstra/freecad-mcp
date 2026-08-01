"""Validation and canonicalization helpers for MCP RPC auth."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from .constants import (
    _NONCE_RE,
    _SAFE_IDENTIFIER_RE,
    _TOKEN_RE,
    MAX_JSON_DEPTH,
    MAX_SECRET_FILE_BYTES,
    MIN_SECRET_BYTES,
)
from .rpc_auth_error import RpcAuthError


def canonical_json_bytes(value: Any) -> bytes:
    """Encode JSON exactly as the addon does for HMAC inputs."""

    _validate_json_value(value, depth=0)
    try:
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise RpcAuthError(
            "INVALID_JSON_VALUE", "Protocol data must be canonical JSON"
        ) from exc
    return rendered.encode("utf-8")


def _validate_json_value(value: Any, *, depth: int) -> None:
    if depth > MAX_JSON_DEPTH:
        raise RpcAuthError(
            "PAYLOAD_TOO_DEEP", "Protocol data exceeds the nesting limit"
        )
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise RpcAuthError(
                "INVALID_JSON_VALUE", "Protocol data must contain finite numbers"
            )
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RpcAuthError(
                    "INVALID_JSON_VALUE", "Protocol object keys must be strings"
                )
            _validate_json_value(item, depth=depth + 1)
        return
    raise RpcAuthError(
        "INVALID_JSON_VALUE", "Protocol data must contain only JSON values"
    )


def _bounded_json(value: Any, limit: int, code: str) -> bytes:
    encoded = canonical_json_bytes(value)
    if len(encoded) > limit:
        raise RpcAuthError(code, "Authenticated RPC payload is too large")
    return encoded


def _require_exact_keys(
    payload: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str] = frozenset(),
    context: str,
) -> None:
    if required.difference(payload):
        raise RpcAuthError("MALFORMED_PAYLOAD", f"{context} is missing required fields")
    if set(payload).difference(required | optional):
        raise RpcAuthError(
            "MALFORMED_PAYLOAD", f"{context} contains unsupported fields"
        )


def _require_identifier(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not _SAFE_IDENTIFIER_RE.fullmatch(value):
        raise RpcAuthError(
            "INVALID_IDENTITY", f"{field_name} is not a valid runtime identifier"
        )
    return value


def _require_uuid(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise RpcAuthError("INVALID_IDENTIFIER", f"{field_name} must be a UUID")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise RpcAuthError(
            "INVALID_IDENTIFIER", f"{field_name} must be a UUID"
        ) from exc
    if parsed.int == 0:
        raise RpcAuthError(
            "INVALID_IDENTIFIER", f"{field_name} must not be the nil UUID"
        )
    return str(parsed)


def _require_pid(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RpcAuthError("INVALID_PID", f"{field_name} must be a positive process ID")
    return value


def _require_port(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise RpcAuthError("INVALID_ENDPOINT", "RPC port must be between 1 and 65535")
    return value


def _require_host(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 255:
        raise RpcAuthError("INVALID_ENDPOINT", "RPC host is invalid")
    if any(ord(char) < 32 for char in value):
        raise RpcAuthError("INVALID_ENDPOINT", "RPC host is invalid")
    return value


def _require_string(value: Any, field_name: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise RpcAuthError(
            "MALFORMED_PAYLOAD", f"{field_name} must be a non-empty string"
        )
    if any(ord(char) < 32 and char != "\t" for char in value):
        raise RpcAuthError(
            "MALFORMED_PAYLOAD", f"{field_name} contains control characters"
        )
    return value


def _require_sequence(value: Any, field_name: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise RpcAuthError("MALFORMED_PAYLOAD", f"{field_name} must be an array")
    return value


def _parse_utc(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise RpcAuthError(
            "INVALID_TIMESTAMP", f"{field_name} must be an RFC3339 timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RpcAuthError(
            "INVALID_TIMESTAMP", f"{field_name} must be an RFC3339 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise RpcAuthError("INVALID_TIMESTAMP", f"{field_name} must include a timezone")
    return parsed.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise RpcAuthError(
            "INVALID_TIMESTAMP", "Runtime timestamps must include a timezone"
        )
    return (
        value.astimezone(UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _validate_nonce(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not _NONCE_RE.fullmatch(value):
        raise RpcAuthError(
            "INVALID_NONCE", f"{field_name} must contain 128-512 bits of randomness"
        )
    import base64

    try:
        decoded = base64.urlsafe_b64decode(value + "=" * ((4 - len(value) % 4) % 4))
    except Exception as exc:
        raise RpcAuthError(
            "INVALID_NONCE", f"{field_name} is not valid base64url"
        ) from exc
    if not 16 <= len(decoded) <= 64:
        raise RpcAuthError(
            "INVALID_NONCE", f"{field_name} must contain 128-512 bits of randomness"
        )
    return value


def _validate_token(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not _TOKEN_RE.fullmatch(value):
        raise RpcAuthError(
            "INVALID_CREDENTIAL", f"{field_name} is not a valid credential"
        )
    return value


def _validate_secret(secret: bytes) -> bytes:
    if (
        not isinstance(secret, bytes)
        or not MIN_SECRET_BYTES <= len(secret) <= MAX_SECRET_FILE_BYTES
    ):
        raise RpcAuthError(
            "INVALID_PROFILE_SECRET",
            f"Profile secret must contain {MIN_SECRET_BYTES}-{MAX_SECRET_FILE_BYTES} bytes",
        )
    return secret


def _normalize_features(value: Sequence[str], field_name: str) -> frozenset[str]:
    sequence = _require_sequence(value, field_name)
    if len(sequence) > 64:
        raise RpcAuthError(
            "MALFORMED_HANDSHAKE", f"{field_name} contains too many entries"
        )
    return frozenset(_require_identifier(item, field_name) for item in sequence)

