"""Authorization-v2 snapshots and terminal byte-identity gate."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
from typing import Any

from .bindings import AuthorizationBinding
from .trusted_bootstrap import _json, _verify
from .validation import ValidationResult

DOCUMENT_FIELDS = {
    "schema_version", "status", "not_before_utc", "issued_utc", "expires_utc",
    *AuthorizationBinding.__annotations__,
}


@dataclass(frozen=True)
class AuthorizationSnapshot:
    document: bytes
    signature: bytes
    binding: AuthorizationBinding
    authorization_sha256: str
    signature_sha256: str


def _instant(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _read(prerequisites: tuple[Path, Path, Path]) -> tuple[bytes, bytes, bytes] | None:
    try:
        document = prerequisites[0].read_bytes()
        signature = base64.b64decode(prerequisites[1].read_bytes(), validate=True)
        parts = prerequisites[2].read_text(encoding="ascii").strip().split()
        if len(parts) < 2 or parts[0] != "ssh-ed25519":
            raise ValueError("public key")
        wire = base64.b64decode(parts[1], validate=True)
        if len(wire) != 51 or wire[:19] != b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20":
            raise ValueError("public key")
        return document, signature, wire[-32:]
    except (OSError, UnicodeError, ValueError, IndexError):
        return None


def capture_initial_authorization(
    prerequisites: tuple[Path, Path, Path],
    expected: AuthorizationBinding,
    reviewer_fingerprint: str | None = None,
    now: datetime | None = None,
) -> tuple[AuthorizationSnapshot | None, ValidationResult]:
    captured = _read(prerequisites)
    if captured is None:
        return None, ValidationResult.fail("authorization", "AUTHORIZATION_SNAPSHOT", "review-authorization.json", "/")
    return capture_initial_authorization_bytes(*captured, expected, reviewer_fingerprint, now)


def capture_initial_authorization_bytes(
    document: bytes,
    signature: bytes,
    key: bytes,
    expected: AuthorizationBinding,
    reviewer_fingerprint: str | None = None,
    now: datetime | None = None,
) -> tuple[AuthorizationSnapshot | None, ValidationResult]:
    """Validate the bootstrap-captured immutable authorization snapshot."""
    try:
        value = _json(document)
    except Exception:
        return None, ValidationResult.fail("authorization", "AUTHORIZATION_SCHEMA", "review-authorization.json", "/")
    if not isinstance(value, dict) or set(value) != DOCUMENT_FIELDS or value.get("schema_version") != 2:
        return None, ValidationResult.fail("authorization", "AUTHORIZATION_SCHEMA", "review-authorization.json", "/")
    if not _verify(key, document, signature):
        return None, ValidationResult.fail("authorization", "AUTHORIZATION_SIGNATURE", "review-authorization.json", "/")
    key_fingerprint = hashlib.sha256(key).hexdigest()
    if value["status"] != "AUTHORIZED":
        return None, ValidationResult.fail("authorization", "AUTHORIZATION_STATUS", "review-authorization.json", "/status")
    if value["reviewer_key"] != key_fingerprint or expected.reviewer_key != key_fingerprint or (reviewer_fingerprint is not None and reviewer_fingerprint != key_fingerprint):
        return None, ValidationResult.fail("authorization", "AUTHORIZATION_REVIEWER", "review-authorization.json", "/reviewer_key")
    if any(value.get(name) != expected_value for name, expected_value in expected.as_dict().items()):
        return None, ValidationResult.fail("authorization", "AUTHORIZATION_BINDING", "review-authorization.json", "/")
    current = now or datetime.now(timezone.utc)
    not_before = _instant(value["not_before_utc"])
    issued = _instant(value["issued_utc"])
    expires = _instant(value["expires_utc"])
    if (
        not_before is None or issued is None or expires is None
        or not_before > issued
        or issued > expires
        or current < not_before
        or issued > current + timedelta(seconds=5)
        or expires < current
        or expires - issued > timedelta(minutes=15)
    ):
        return None, ValidationResult.fail("authorization", "AUTHORIZATION_EXPIRED", "review-authorization.json", "/expires_utc")
    return AuthorizationSnapshot(
        document,
        signature,
        expected,
        hashlib.sha256(document).hexdigest(),
        hashlib.sha256(signature).hexdigest(),
    ), ValidationResult.ok()


def capture_terminal_authorization(
    prerequisites: tuple[Path, Path, Path],
    initial: AuthorizationSnapshot,
    now: datetime | None = None,
) -> tuple[AuthorizationSnapshot | None, ValidationResult]:
    terminal, result = capture_initial_authorization(prerequisites, initial.binding, initial.binding.reviewer_key, now)
    if not result.passed or terminal is None:
        return None, result
    if terminal.document != initial.document or terminal.signature != initial.signature:
        return None, ValidationResult.fail("terminal_authorization", "AUTHORIZATION_CHANGED", "review-authorization.json", "/")
    return terminal, ValidationResult.ok()
