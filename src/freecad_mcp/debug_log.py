"""Bounded, redacted MCP debug logging (R1).

Debug logging is opt-in via ``FREECAD_MCP_DEBUG=1``. By default only metadata
(hashes, byte counts, tool names, timing, status) is written — never full code
bodies or base64 image payloads.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

logger = logging.getLogger("FreeCADMCPserver.debug")

_DEFAULT_LOG_PATH = Path(os.environ.get("FREECAD_MCP_DEBUG_LOG", "mcp_debug.log"))
_REDACT_CODE = os.environ.get("FREECAD_MCP_DEBUG_REDACT_CODE", "1") != "0"
_REDACT_IMAGES = os.environ.get("FREECAD_MCP_DEBUG_REDACT_IMAGES", "1") != "0"

_BASE64_RE = re.compile(r'"data"\s*:\s*"[A-Za-z0-9+/=\s]{200,}"')
_CODE_FIELD_RE = re.compile(r'("code"\s*:\s*")([^"]*)(")', re.DOTALL)
_IMAGE_MIME_RE = re.compile(
    r'("mimeType"\s*:\s*"image/[^"]+"\s*,\s*"data"\s*:\s*")([^"]*)(")',
    re.DOTALL,
)
_SENSITIVE_FIELD_NAMES = frozenset(
    {
        "auth_secret",
        "auth_token",
        "bearer_token",
        "client_proof",
        "hmac",
        "lease_token",
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


def debug_enabled() -> bool:
    return os.environ.get("FREECAD_MCP_DEBUG", "0") == "1"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def _is_sensitive_field(key: Any) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    return (
        normalized in _SENSITIVE_FIELD_NAMES
        or normalized.endswith(
            (
                "_fingerprint",
                "_password",
                "_proof",
                "_secret",
                "_signature",
                "_token",
            )
        )
    )


def _collect_sensitive_values(value: Any, secrets_out: set[str]) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if _is_sensitive_field(key):
                _collect_secret_strings(child, secrets_out)
                continue
            _collect_sensitive_values(child, secrets_out)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _collect_sensitive_values(child, secrets_out)


def _collect_secret_strings(value: Any, secrets_out: set[str]) -> None:
    if isinstance(value, str):
        if value:
            secrets_out.add(value)
        return
    if isinstance(value, Mapping):
        for child in value.values():
            _collect_secret_strings(child, secrets_out)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _collect_secret_strings(child, secrets_out)


def _redact_text(value: Any, secrets: Iterable[str]) -> str:
    safe = str(value)
    for secret in secrets:
        if secret:
            safe = safe.replace(secret, "[REDACTED]")
    return safe


def _redact_structure(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, Mapping):
        return {
            _redact_text(key, secrets): (
                "<redacted>"
                if _is_sensitive_field(key)
                else _redact_structure(child, secrets)
            )
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_redact_structure(child, secrets) for child in value]
    if isinstance(value, tuple):
        return [_redact_structure(child, secrets) for child in value]
    if isinstance(value, str):
        return _redact_text(value, secrets)
    return value


def _json_safe(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return str(value)


def _known_secrets(payload: Any, supplied: Iterable[str]) -> tuple[str, ...]:
    found = {str(secret) for secret in supplied if secret}
    _collect_sensitive_values(payload, found)
    # Replace longer values first so overlapping credentials cannot leave a
    # recognizable suffix after a shorter value is removed.
    return tuple(sorted(found, key=len, reverse=True))


def redact_payload(payload: Any, *, secrets: Iterable[str] = ()) -> Any:
    """Return a log-safe copy of *payload* with credential/code data redacted.

    Sensitive values discovered under credential-shaped keys are also removed
    from arbitrary nested messages. Callers may supply additional exact bearer
    values when a secret is not otherwise present in the payload structure.
    """
    if payload is None:
        return None
    serializable = _json_safe(payload)
    known_secrets = _known_secrets(serializable, secrets)
    structurally_redacted = _redact_structure(serializable, known_secrets)
    text = json.dumps(structurally_redacted, ensure_ascii=False, default=str)

    original_len = len(text)
    redacted = text

    if _REDACT_CODE:
        def _code_sub(m: re.Match[str]) -> str:
            body = m.group(2)
            return f'{m.group(1)}<redacted code sha256={_sha256(body)} len={len(body)}>{m.group(3)}'

        redacted = _CODE_FIELD_RE.sub(_code_sub, redacted)

    if _REDACT_IMAGES:
        def _img_sub(m: re.Match[str]) -> str:
            body = m.group(2)
            return f'{m.group(1)}<redacted image sha256={_sha256(body)} len={len(body)}>{m.group(3)}'

        redacted = _IMAGE_MIME_RE.sub(_img_sub, redacted)
        redacted = _BASE64_RE.sub(
            lambda m: m.group(0).split('"data"')[0]
            + '"data":"<redacted base64>"',
            redacted,
        )

    try:
        return json.loads(redacted)
    except Exception:
        if len(redacted) > 4096:
            return {
                "redacted": True,
                "sha256": _sha256(text),
                "bytes": original_len,
                "preview": redacted[:512] + "…",
            }
        return redacted


def _max_log_bytes() -> int:
    return int(os.environ.get("FREECAD_MCP_DEBUG_MAX_BYTES", str(512 * 1024)))


def _rotate_if_needed(path: Path) -> None:
    try:
        max_bytes = _max_log_bytes()
        if path.exists() and path.stat().st_size >= max_bytes:
            backup = path.parent / (path.name + ".1")
            if backup.exists():
                backup.unlink()
            path.replace(backup)
    except OSError as exc:
        logger.warning("Failed to rotate debug log %s: %s", path, exc)


def log_event(
    direction: str,
    *,
    method: str | None = None,
    tool: str | None = None,
    payload: Any = None,
    status: str | None = None,
    duration_ms: float | None = None,
    error: str | None = None,
    path: Path | None = None,
    secrets: Iterable[str] = (),
) -> None:
    if not debug_enabled():
        return
    log_path = path or _DEFAULT_LOG_PATH
    entry: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "direction": direction,
    }
    if method:
        entry["method"] = method
    if tool:
        entry["tool"] = tool
    if status:
        entry["status"] = status
    if duration_ms is not None:
        entry["duration_ms"] = round(duration_ms, 2)
    serializable_payload = _json_safe(payload) if payload is not None else None
    known_secrets = _known_secrets(serializable_payload, secrets)
    if error:
        entry["error"] = _redact_text(error, known_secrets)
    if payload is not None:
        safe = redact_payload(serializable_payload, secrets=known_secrets)
        raw = json.dumps(safe, ensure_ascii=False, default=str)
        entry["payload_sha256"] = _sha256(raw)
        entry["payload_bytes"] = len(raw)
        entry["payload"] = safe

    line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        _rotate_if_needed(log_path)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError as exc:
        logger.warning("Failed to write debug log: %s", exc)
