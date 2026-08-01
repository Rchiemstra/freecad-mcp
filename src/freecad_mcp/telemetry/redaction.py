"""Credential, source-code, and binary-payload redaction."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping
from typing import Any

SENSITIVE_FIELD_NAMES = frozenset(
    {
        "auth_secret",
        "auth_token",
        "bearer_token",
        "client_proof",
        "hmac",
        "lease_token",
        "operation_signature",
        "password",
        "private_key",
        "profile_secret",
        "proof",
        "rpc_session_token",
        "secret",
        "secret_fingerprint",
        "server_proof",
        "session_token",
        "signature",
        "token",
        "token_digest",
        "token_fingerprint",
    }
)
CODE_FIELDS = frozenset({"code", "python", "script", "source_code"})
IMAGE_FIELDS = frozenset(
    {"base64", "data", "image", "image_base64", "screenshot", "screenshots"}
)


def _sha256(value: str | bytes) -> str:
    raw = value if isinstance(value, bytes) else value.encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()


def _field_name(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_")


def is_sensitive_field(value: Any) -> bool:
    name = _field_name(value)
    return name in SENSITIVE_FIELD_NAMES or name.endswith(
        ("_password", "_proof", "_secret", "_signature", "_token")
    )


def _collect_secrets(value: Any, output: set[str]) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if is_sensitive_field(key):
                _collect_secret_values(child, output)
            else:
                _collect_secrets(child, output)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _collect_secrets(child, output)


def _collect_secret_values(value: Any, output: set[str]) -> None:
    if isinstance(value, str) and value:
        output.add(value)
    elif isinstance(value, Mapping):
        for child in value.values():
            _collect_secret_values(child, output)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _collect_secret_values(child, output)


def _replace_secrets(value: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        value = value.replace(secret, "[REDACTED]")
    return value


def _binary_summary(value: Any, kind: str) -> dict[str, Any]:
    raw = (
        value
        if isinstance(value, bytes)
        else str(value).encode("utf-8", errors="replace")
    )
    return {
        "redacted": True,
        "kind": kind,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _redact(value: Any, secrets: tuple[str, ...], field: str = "") -> Any:
    normalized_field = _field_name(field)
    if is_sensitive_field(normalized_field):
        return "<redacted>"
    if normalized_field in CODE_FIELDS:
        return _binary_summary(value, "code")
    if normalized_field in IMAGE_FIELDS and (
        isinstance(value, (bytes, bytearray))
        or (isinstance(value, str) and len(value) >= 128)
    ):
        return _binary_summary(value, "binary")
    if isinstance(value, Mapping):
        return {
            _replace_secrets(str(key), secrets): _redact(child, secrets, str(key))
            for key, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(child, secrets, field) for child in value]
    if isinstance(value, bytes):
        return _binary_summary(value, "binary")
    if isinstance(value, str):
        return _replace_secrets(value, secrets)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _replace_secrets(str(value), secrets)


def _max_payload_bytes() -> int:
    raw = os.environ.get("FREECAD_MCP_TELEMETRY_MAX_PAYLOAD_BYTES", "65536")
    try:
        return max(1024, int(raw))
    except ValueError:
        return 65536


def redact_payload(value: Any, *, secrets: Iterable[str] = ()) -> Any:
    discovered = {str(item) for item in secrets if item}
    _collect_secrets(value, discovered)
    ordered = tuple(sorted(discovered, key=len, reverse=True))
    redacted = _redact(value, ordered)
    raw = json.dumps(redacted, ensure_ascii=False, default=str).encode("utf-8")
    maximum = _max_payload_bytes()
    if len(raw) <= maximum:
        return redacted
    preview = raw[: min(512, maximum)].decode("utf-8", errors="replace")
    return {
        "truncated": True,
        "original_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "preview": preview,
    }


__all__ = ["SENSITIVE_FIELD_NAMES", "is_sensitive_field", "redact_payload"]
