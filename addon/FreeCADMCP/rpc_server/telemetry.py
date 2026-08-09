"""FreeCAD-process lifecycle telemetry using the shared event-v1 shape.

The addon can be installed without the Python MCP distribution, so this module
has no package dependency.  Correlation identifiers are supplied explicitly by
the authenticated RPC/GUI/worker boundaries and credential-shaped payload
fields are removed before writing.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SESSION_ID = str(uuid.uuid4())
_SEQUENCE = 0
_LOCK = threading.RLock()
_SENSITIVE = {
    "auth_secret",
    "client_proof",
    "lease_token",
    "operation_signature",
    "password",
    "proof",
    "rpc_session_token",
    "server_proof",
    "session_token",
    "signature",
    "token",
}
_CODE_FIELDS = {"code", "python", "script", "source_code"}
_IMAGE_FIELDS = {
    "base64",
    "data",
    "image",
    "image_base64",
    "screenshot",
    "screenshots",
}


def _timestamp() -> str:
    return (
        datetime.now(UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _path() -> Path:
    explicit = os.environ.get("FREECAD_MCP_ADDON_TELEMETRY_FILE")
    if explicit:
        return Path(explicit)
    directory = Path(
        os.environ.get("FREECAD_MCP_DEBUG_LOG_DIR")
        or os.environ.get("FREECAD_MCP_TELEMETRY_DIR")
        or "debug_logs"
    )
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    return directory / (
        f"addon_debug_{date}_{os.getpid()}_{_SESSION_ID.replace('-', '')[:12]}.jsonl"
    )


def _is_sensitive(field: str) -> bool:
    normalized = str(field).lower().replace("-", "_")
    return normalized in _SENSITIVE or normalized.endswith(
        ("_password", "_proof", "_secret", "_signature", "_token")
    )


def _collect_secret_values(value: Any, output: set[str]) -> None:
    if isinstance(value, str) and value:
        output.add(value)
    elif isinstance(value, Mapping):
        for child in value.values():
            _collect_secret_values(child, output)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _collect_secret_values(child, output)


def _collect_secrets(value: Any, output: set[str]) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if _is_sensitive(str(key)):
                _collect_secret_values(child, output)
            else:
                _collect_secrets(child, output)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _collect_secrets(child, output)


def _replace_secrets(value: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        value = value.replace(secret, "[REDACTED]")
    return value


def _summary(value: Any, kind: str) -> dict[str, Any]:
    raw = (
        bytes(value)
        if isinstance(value, (bytes, bytearray))
        else str(value).encode("utf-8", errors="replace")
    )
    return {
        "redacted": True,
        "kind": kind,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _redact(value: Any, field: str = "", secrets: tuple[str, ...] = ()) -> Any:
    normalized = str(field).lower().replace("-", "_")
    if _is_sensitive(normalized):
        return "<redacted>"
    if normalized in _CODE_FIELDS:
        return _summary(value, "code")
    if normalized in _IMAGE_FIELDS and (
        isinstance(value, (bytes, bytearray))
        or (isinstance(value, str) and len(value) >= 128)
    ):
        return _summary(value, "binary")
    if isinstance(value, Mapping):
        return {
            _replace_secrets(str(key), secrets): _redact(
                child, str(key), secrets
            )
            for key, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(child, field, secrets) for child in value]
    if isinstance(value, (bytes, bytearray)):
        return _summary(value, "binary")
    if isinstance(value, str):
        return _replace_secrets(value, secrets)
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return _replace_secrets(str(value), secrets)


def _positive_environment(name: str, fallback: int, minimum: int) -> int:
    try:
        return max(minimum, int(os.environ.get(name, str(fallback))))
    except ValueError:
        return fallback


def _safe_payload(
    payload: Mapping[str, Any],
    *,
    secrets: Iterable[str],
) -> Mapping[str, Any]:
    discovered = {str(item) for item in secrets if item}
    _collect_secrets(payload, discovered)
    ordered = tuple(sorted(discovered, key=len, reverse=True))
    redacted = _redact(dict(payload), secrets=ordered)
    encoded = json.dumps(redacted, ensure_ascii=False, default=str).encode("utf-8")
    maximum = _positive_environment(
        "FREECAD_MCP_TELEMETRY_MAX_PAYLOAD_BYTES", 65536, 1024
    )
    if len(encoded) <= maximum:
        return redacted
    return {
        "truncated": True,
        "original_bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "preview": encoded[: min(512, maximum)].decode(
            "utf-8", errors="replace"
        ),
    }


def _rotate(destination: Path) -> None:
    maximum = _positive_environment(
        "FREECAD_MCP_TELEMETRY_MAX_BYTES", 8 * 1024 * 1024, 4096
    )
    if not destination.exists() or destination.stat().st_size < maximum:
        return
    count = min(
        10,
        _positive_environment("FREECAD_MCP_TELEMETRY_BACKUPS", 3, 1),
    )
    oldest = destination.with_name(f"{destination.name}.{count}")
    if oldest.exists():
        oldest.unlink()
    for index in range(count - 1, 0, -1):
        source = destination.with_name(f"{destination.name}.{index}")
        if source.exists():
            source.replace(
                destination.with_name(f"{destination.name}.{index + 1}")
            )
    destination.replace(destination.with_name(f"{destination.name}.1"))


def emit(
    source: str,
    event: str,
    *,
    status: str = "succeeded",
    duration_ms: float | None = None,
    error_code: str | None = None,
    payload: Mapping[str, Any] | None = None,
    session_id: str | None = None,
    task_id: str | None = None,
    call_id: str | None = None,
    request_id: str | None = None,
    execution_id: str | None = None,
    worker_job_id: str | None = None,
    document_session_uuid: str | None = None,
    recovery_incident_id: str | None = None,
    secrets: Iterable[str] = (),
) -> dict[str, Any] | None:
    if os.environ.get("FREECAD_MCP_TELEMETRY", "1") == "0":
        return None
    global _SEQUENCE
    with _LOCK:
        _SEQUENCE += 1
        entry = {
            "schema_version": 1,
            "timestamp": _timestamp(),
            "monotonic_ns": time.monotonic_ns(),
            "sequence": _SEQUENCE,
            "source": str(source),
            "event": str(event),
            "status": str(status),
            "session_id": str(session_id or _SESSION_ID),
            "task_id": task_id,
            "call_id": call_id,
            "attempt_number": None,
            "parent_call_id": None,
            "request_id": request_id,
            "execution_id": execution_id,
            "worker_job_id": worker_job_id,
            "document_session_uuid": document_session_uuid,
            "recovery_incident_id": recovery_incident_id,
            "duration_ms": (
                None if duration_ms is None else round(float(duration_ms), 3)
            ),
            "error_code": error_code,
            "payload": _safe_payload(payload or {}, secrets=secrets),
        }
        line = json.dumps(
            entry,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            default=str,
        ) + "\n"
        destination = _path()
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            _rotate(destination)
            with destination.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line)
                handle.flush()
        except OSError:
            return None
        return entry


__all__ = ["emit"]
