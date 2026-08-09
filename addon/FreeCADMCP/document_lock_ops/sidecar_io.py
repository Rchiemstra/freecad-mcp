from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .constants import SIDECAR_SUFFIX
from .lease_record import LeaseRecord


def sidecar_path_for(file_path: str) -> Path:
    return Path(f"{file_path}{SIDECAR_SUFFIX}")


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Same idiom as worker_protocol.write_json_atomic (no size cap)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(tmp_name)
        raise


def _create_sidecar_exclusive(path: Path, payload: dict[str, Any]) -> bool:
    """Atomically create a sidecar. Returns False if it already exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(path), flags)
    except FileExistsError:
        return False
    except OSError as exc:
        # Windows may raise EEXIST-equivalent
        if getattr(exc, "errno", None) in (getattr(os, "EEXIST", 17), 17):
            return False
        raise
    try:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        os.write(fd, encoded)
        os.fsync(fd)
    finally:
        os.close(fd)
    return True


def _read_sidecar(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


_SENSITIVE_SIDECAR_FIELDS = frozenset(
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


def _is_sensitive_sidecar_field(key: Any) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    return normalized in _SENSITIVE_SIDECAR_FIELDS or normalized.endswith(
        ("_password", "_proof", "_secret", "_signature", "_token")
    )


def _collect_sidecar_secrets(value: Any, secrets_out: set[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if _is_sensitive_sidecar_field(key):
                _collect_secret_strings(child, secrets_out)
                continue
            _collect_sidecar_secrets(child, secrets_out)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _collect_sidecar_secrets(child, secrets_out)


def _collect_secret_strings(value: Any, secrets_out: set[str]) -> None:
    if isinstance(value, str):
        if value:
            secrets_out.add(value)
        return
    if isinstance(value, dict):
        for child in value.values():
            _collect_secret_strings(child, secrets_out)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _collect_secret_strings(child, secrets_out)


def _redact_sidecar_diagnostic(value: Any, secrets: set[str]) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                "<redacted>"
                if _is_sensitive_sidecar_field(key)
                else _redact_sidecar_diagnostic(child, secrets)
            )
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_redact_sidecar_diagnostic(child, secrets) for child in value]
    if isinstance(value, tuple):
        return [_redact_sidecar_diagnostic(child, secrets) for child in value]
    if isinstance(value, str):
        safe = value
        for secret in secrets:
            safe = safe.replace(secret, "[REDACTED]")
        return safe
    return value


def _public_sidecar_payload(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    try:
        return LeaseRecord.from_dict(data).to_dict()
    except Exception:
        secrets_found: set[str] = set()
        _collect_sidecar_secrets(data, secrets_found)
        return _redact_sidecar_diagnostic(data, secrets_found)


def _remove_sidecar(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except TypeError:
        # Python < 3.8 compatibility (FreeCAD may ship older)
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass
    except OSError:
        pass
