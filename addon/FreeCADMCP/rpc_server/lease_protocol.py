"""Authenticated protocol-v2 primitives for the FreeCAD MCP RPC server.

This module deliberately depends only on the Python standard library.  It can
therefore be imported by setup tools, tests, and FreeCAD's embedded Python
without importing FreeCAD or Qt.

The protocol authenticates an MCP runtime to one specific FreeCAD addon
runtime.  It is a cooperative local-RPC boundary, not transport encryption or
process attestation.  Non-loopback deployments still require an encrypted
tunnel or TLS proxy.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


PROTOCOL_NAME = "freecad-mcp-rpc"
PROTOCOL_VERSION = 2
HANDSHAKE_REQUEST_KIND = "freecad-mcp-handshake-v2"
HANDSHAKE_RESPONSE_KIND = "freecad-mcp-handshake-v2-response"
HMAC_ALGORITHM = "hmac-sha256"

SUPPORTED_FEATURES = (
    "authenticated_sessions",
    "document_session_identity",
    "lease_credentials_v2",
    "request_idempotency",
    "runtime_binding",
)
REQUIRED_PROTOCOL_FEATURES = frozenset(
    {
        "authenticated_sessions",
        "lease_credentials_v2",
        "runtime_binding",
    }
)

DEFAULT_SESSION_TTL_SECONDS = 5 * 60.0
MAX_SESSION_TTL_SECONDS = 60 * 60.0
DEFAULT_REPLAY_TTL_SECONDS = 10 * 60.0
DEFAULT_REPLAY_RESPONSE_MAX_BYTES = 64 * 1024
MAX_HANDSHAKE_BYTES = 64 * 1024
MAX_ENVELOPE_BYTES = 1024 * 1024
MAX_SECRET_FILE_BYTES = 4096
MIN_SECRET_BYTES = 32
MAX_LEASE_CREDENTIALS = 32
MAX_PARAMS_DEPTH = 32
MAX_HANDSHAKE_NONCES = 65_536

_PROCESS_STARTED_AT = datetime.now(timezone.utc)
_METHOD_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+\-=]{0,255}$")
_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{22,128}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,512}$")
_PROOF_RE = re.compile(r"^hmac-sha256:([0-9a-f]{64})$")

_REQUEST_PROOF_DOMAIN = b"freecad-mcp-rpc-v2\x00handshake-request\x00"
_RESPONSE_PROOF_DOMAIN = b"freecad-mcp-rpc-v2\x00handshake-response\x00"

_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "auth_secret",
        "credential",
        "credentials",
        "hmac",
        "lease_token",
        "password",
        "proof",
        "secret",
        "secret_fingerprint",
        "session_token",
        "token",
        "token_digest",
        "token_fingerprint",
    }
)
_REDACTED = "<redacted>"


class LeaseProtocolError(ValueError):
    """A protocol rejection with a stable, non-secret public representation."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.code = str(code)
        self.public_message = str(message)
        self.details = dict(details or {})
        super().__init__(f"{self.code}: {self.public_message}")

    def to_public_dict(self, *, request_id: str | None = None) -> dict[str, Any]:
        error: dict[str, Any] = {
            "code": self.code,
            "message": self.public_message,
        }
        if self.details:
            error["details"] = redact_sensitive(self.details)
        result: dict[str, Any] = {"ok": False, "error": error}
        if request_id is not None and _is_uuid(request_id):
            result["request_id"] = str(uuid.UUID(request_id))
        return result


def public_error(
    error: BaseException,
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Return a bounded error payload without exception internals or secrets."""

    if isinstance(error, LeaseProtocolError):
        return error.to_public_dict(request_id=request_id)
    result: dict[str, Any] = {
        "ok": False,
        "error": {
            "code": "INTERNAL_PROTOCOL_ERROR",
            "message": "The authenticated RPC request could not be processed",
        },
    }
    if request_id is not None and _is_uuid(request_id):
        result["request_id"] = str(uuid.UUID(request_id))
    return result


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


def canonical_json_bytes(value: Any) -> bytes:
    """Encode a JSON value deterministically for HMAC and fingerprints."""

    _validate_json_value(value, depth=0)
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise LeaseProtocolError(
            "INVALID_JSON_VALUE", "Protocol data must be canonical JSON"
        ) from exc
    return text.encode("utf-8")


def _validate_json_value(value: Any, *, depth: int) -> None:
    if depth > MAX_PARAMS_DEPTH:
        raise LeaseProtocolError(
            "PAYLOAD_TOO_DEEP", "Protocol data exceeds the nesting limit"
        )
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise LeaseProtocolError(
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
                raise LeaseProtocolError(
                    "INVALID_JSON_VALUE", "Protocol object keys must be strings"
                )
            _validate_json_value(item, depth=depth + 1)
        return
    raise LeaseProtocolError(
        "INVALID_JSON_VALUE", "Protocol data must contain only JSON values"
    )


def _limited_canonical_json(value: Any, limit: int, code: str) -> bytes:
    encoded = canonical_json_bytes(value)
    if len(encoded) > limit:
        raise LeaseProtocolError(code, "Authenticated RPC payload is too large")
    return encoded


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise LeaseProtocolError(
            "INVALID_TIMESTAMP", "Runtime timestamps must include a timezone"
        )
    normalized = value.astimezone(timezone.utc)
    return normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise LeaseProtocolError(
            "INVALID_TIMESTAMP", f"{field_name} must be an RFC3339 timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LeaseProtocolError(
            "INVALID_TIMESTAMP", f"{field_name} must be an RFC3339 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise LeaseProtocolError(
            "INVALID_TIMESTAMP", f"{field_name} must include a timezone"
        )
    return parsed.astimezone(timezone.utc)


def _require_identifier(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not _SAFE_IDENTIFIER_RE.fullmatch(value):
        raise LeaseProtocolError(
            "INVALID_IDENTITY", f"{field_name} is not a valid runtime identifier"
        )
    return value


def _require_uuid(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise LeaseProtocolError(
            "INVALID_IDENTIFIER", f"{field_name} must be a UUID"
        )
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise LeaseProtocolError(
            "INVALID_IDENTIFIER", f"{field_name} must be a UUID"
        ) from exc
    if parsed.int == 0:
        raise LeaseProtocolError(
            "INVALID_IDENTIFIER", f"{field_name} must not be the nil UUID"
        )
    return str(parsed)


def _is_uuid(value: Any) -> bool:
    try:
        return bool(value) and uuid.UUID(str(value)).int != 0
    except (ValueError, TypeError, AttributeError):
        return False


def _require_pid(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise LeaseProtocolError(
            "INVALID_PID", f"{field_name} must be a positive process ID"
        )
    return value


def _require_port(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise LeaseProtocolError(
            "INVALID_ENDPOINT", "RPC port must be between 1 and 65535"
        )
    return value


def _require_host(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 255:
        raise LeaseProtocolError("INVALID_ENDPOINT", "RPC host is invalid")
    if any(ord(char) < 32 for char in value):
        raise LeaseProtocolError("INVALID_ENDPOINT", "RPC host is invalid")
    return value


def _require_exact_keys(
    payload: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str] = frozenset(),
    context: str,
) -> None:
    missing = required.difference(payload)
    unknown = set(payload).difference(required | optional)
    if missing:
        raise LeaseProtocolError(
            "MALFORMED_PAYLOAD", f"{context} is missing required fields"
        )
    if unknown:
        raise LeaseProtocolError(
            "MALFORMED_PAYLOAD", f"{context} contains unsupported fields"
        )


def _require_string(value: Any, field_name: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise LeaseProtocolError(
            "MALFORMED_PAYLOAD", f"{field_name} must be a non-empty string"
        )
    if any(ord(char) < 32 and char not in "\t" for char in value):
        raise LeaseProtocolError(
            "MALFORMED_PAYLOAD", f"{field_name} contains control characters"
        )
    return value


def _require_sequence(value: Any, field_name: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise LeaseProtocolError(
            "MALFORMED_PAYLOAD", f"{field_name} must be an array"
        )
    return value


def _validate_nonce(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not _NONCE_RE.fullmatch(value):
        raise LeaseProtocolError(
            "INVALID_NONCE", f"{field_name} must contain 128-512 bits of randomness"
        )
    padding = "=" * ((4 - len(value) % 4) % 4)
    try:
        import base64

        decoded = base64.urlsafe_b64decode(value + padding)
    except Exception as exc:
        raise LeaseProtocolError(
            "INVALID_NONCE", f"{field_name} is not valid base64url"
        ) from exc
    if not 16 <= len(decoded) <= 64:
        raise LeaseProtocolError(
            "INVALID_NONCE", f"{field_name} must contain 128-512 bits of randomness"
        )
    return value


def _validate_secret(secret: bytes) -> bytes:
    if not isinstance(secret, bytes) or not MIN_SECRET_BYTES <= len(secret) <= MAX_SECRET_FILE_BYTES:
        raise LeaseProtocolError(
            "INVALID_PROFILE_SECRET",
            f"Profile secret must contain {MIN_SECRET_BYTES}-{MAX_SECRET_FILE_BYTES} bytes",
        )
    return secret


def load_profile_secret(
    path: str | os.PathLike[str],
    *,
    require_owner_only: bool = True,
) -> bytes:
    """Load a bounded regular-file secret and enforce POSIX ownership/mode.

    Python's standard library does not provide a portable Windows DACL reader.
    On Windows this function still rejects links, non-regular files, and unsafe
    sizes; the profile setup code must create an owner-only DACL.
    """

    secret_path = Path(path)
    try:
        before = secret_path.lstat()
    except OSError as exc:
        raise LeaseProtocolError(
            "PROFILE_SECRET_UNAVAILABLE", "Profile authentication secret is unavailable"
        ) from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise LeaseProtocolError(
            "INSECURE_PROFILE_SECRET", "Profile authentication secret must be a regular file"
        )
    if not MIN_SECRET_BYTES <= before.st_size <= MAX_SECRET_FILE_BYTES:
        raise LeaseProtocolError(
            "INVALID_PROFILE_SECRET", "Profile authentication secret has an invalid size"
        )
    if require_owner_only and os.name != "nt":
        if before.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise LeaseProtocolError(
                "INSECURE_PROFILE_SECRET",
                "Profile authentication secret must be accessible only to its owner",
            )
        if hasattr(os, "geteuid") and before.st_uid != os.geteuid():
            raise LeaseProtocolError(
                "INSECURE_PROFILE_SECRET",
                "Profile authentication secret must be owned by the current user",
            )
    try:
        with secret_path.open("rb") as handle:
            value = handle.read(MAX_SECRET_FILE_BYTES + 1)
            after = os.fstat(handle.fileno())
    except OSError as exc:
        raise LeaseProtocolError(
            "PROFILE_SECRET_UNAVAILABLE", "Profile authentication secret is unavailable"
        ) from exc
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise LeaseProtocolError(
            "PROFILE_SECRET_CHANGED", "Profile authentication secret changed while loading"
        )
    return _validate_secret(value)


def create_profile_secret(
    path: str | os.PathLike[str],
    *,
    num_bytes: int = 32,
) -> bytes:
    """Create a new secret without overwriting an existing profile secret."""

    if not MIN_SECRET_BYTES <= num_bytes <= MAX_SECRET_FILE_BYTES:
        raise LeaseProtocolError(
            "INVALID_PROFILE_SECRET", "Requested profile secret size is invalid"
        )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_bytes(num_bytes)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        descriptor = os.open(target, flags, 0o600)
    except OSError as exc:
        raise LeaseProtocolError(
            "PROFILE_SECRET_CREATE_FAILED",
            "Profile authentication secret could not be created",
        ) from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            os.chmod(target, 0o600)
    except Exception:
        try:
            target.unlink()
        except OSError:
            pass
        raise
    return value


@dataclass(frozen=True)
class RuntimeManifest:
    """Identity of the exact FreeCAD addon runtime accepting RPC requests."""

    profile_id: str
    addon_runtime_id: str
    freecad_pid: int
    freecad_process_started_at: str
    boot_id: str
    rpc_host: str
    rpc_port: int
    freecad_version: str
    freecad_revision: str
    addon_version: str
    addon_build_id: str
    profile_path_fingerprint: str
    protocol_version: int = PROTOCOL_VERSION
    features: tuple[str, ...] = field(default_factory=lambda: SUPPORTED_FEATURES)

    def __post_init__(self) -> None:
        _require_identifier(self.profile_id, "profile_id")
        object.__setattr__(
            self, "addon_runtime_id", _require_uuid(self.addon_runtime_id, "addon_runtime_id")
        )
        _require_pid(self.freecad_pid, "freecad_pid")
        _parse_utc(self.freecad_process_started_at, "freecad_process_started_at")
        _require_identifier(self.boot_id, "boot_id")
        _require_host(self.rpc_host)
        _require_port(self.rpc_port)
        for field_name in (
            "freecad_version",
            "freecad_revision",
            "addon_version",
            "addon_build_id",
        ):
            _require_string(getattr(self, field_name), field_name, maximum=256)
        _require_identifier(self.profile_path_fingerprint, "profile_path_fingerprint")
        if self.protocol_version != PROTOCOL_VERSION:
            raise LeaseProtocolError(
                "UNSUPPORTED_PROTOCOL", "Runtime manifest protocol version is unsupported"
            )
        normalized_features = _normalize_features(self.features, "features")
        if not REQUIRED_PROTOCOL_FEATURES.issubset(normalized_features):
            raise LeaseProtocolError(
                "MISSING_PROTOCOL_FEATURE",
                "Runtime manifest omits a required protocol feature",
            )
        object.__setattr__(self, "features", tuple(sorted(normalized_features)))

    @property
    def endpoint(self) -> str:
        host = f"[{self.rpc_host}]" if ":" in self.rpc_host else self.rpc_host
        return f"{host}:{self.rpc_port}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_name": PROTOCOL_NAME,
            "protocol_version": self.protocol_version,
            "features": list(self.features),
            "profile_id": self.profile_id,
            "addon_runtime_id": self.addon_runtime_id,
            "freecad_pid": self.freecad_pid,
            "freecad_process_started_at": self.freecad_process_started_at,
            "boot_id": self.boot_id,
            "rpc_host": self.rpc_host,
            "rpc_port": self.rpc_port,
            "endpoint": self.endpoint,
            "freecad_version": self.freecad_version,
            "freecad_revision": self.freecad_revision,
            "addon_version": self.addon_version,
            "addon_build_id": self.addon_build_id,
            "profile_path_fingerprint": self.profile_path_fingerprint,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimeManifest":
        if not isinstance(payload, Mapping):
            raise LeaseProtocolError(
                "MALFORMED_MANIFEST", "Runtime manifest must be an object"
            )
        _require_exact_keys(
            payload,
            required={
                "protocol_name",
                "protocol_version",
                "features",
                "profile_id",
                "addon_runtime_id",
                "freecad_pid",
                "freecad_process_started_at",
                "boot_id",
                "rpc_host",
                "rpc_port",
                "endpoint",
                "freecad_version",
                "freecad_revision",
                "addon_version",
                "addon_build_id",
                "profile_path_fingerprint",
            },
            context="runtime manifest",
        )
        if payload["protocol_name"] != PROTOCOL_NAME:
            raise LeaseProtocolError(
                "UNSUPPORTED_PROTOCOL", "Runtime manifest protocol name is unsupported"
            )
        manifest = cls(
            protocol_version=payload["protocol_version"],
            features=tuple(_require_sequence(payload["features"], "features")),
            profile_id=payload["profile_id"],
            addon_runtime_id=payload["addon_runtime_id"],
            freecad_pid=payload["freecad_pid"],
            freecad_process_started_at=payload["freecad_process_started_at"],
            boot_id=payload["boot_id"],
            rpc_host=payload["rpc_host"],
            rpc_port=payload["rpc_port"],
            freecad_version=payload["freecad_version"],
            freecad_revision=payload["freecad_revision"],
            addon_version=payload["addon_version"],
            addon_build_id=payload["addon_build_id"],
            profile_path_fingerprint=payload["profile_path_fingerprint"],
        )
        if payload["endpoint"] != manifest.endpoint:
            raise LeaseProtocolError(
                "INSTANCE_MISMATCH", "Runtime manifest endpoint is inconsistent"
            )
        return manifest


def make_runtime_manifest(
    *,
    profile_id: str,
    addon_runtime_id: str | None = None,
    freecad_pid: int | None = None,
    freecad_process_started_at: str | None = None,
    boot_id: str,
    rpc_host: str,
    rpc_port: int,
    freecad_version: str,
    freecad_revision: str,
    addon_version: str,
    addon_build_id: str,
    profile_path_fingerprint: str,
    features: Sequence[str] = SUPPORTED_FEATURES,
) -> RuntimeManifest:
    """Construct a validated manifest, supplying safe runtime defaults."""

    return RuntimeManifest(
        profile_id=profile_id,
        addon_runtime_id=addon_runtime_id or str(uuid.uuid4()),
        freecad_pid=os.getpid() if freecad_pid is None else freecad_pid,
        freecad_process_started_at=freecad_process_started_at
        or _format_utc(_PROCESS_STARTED_AT),
        boot_id=boot_id,
        rpc_host=rpc_host,
        rpc_port=rpc_port,
        freecad_version=freecad_version,
        freecad_revision=freecad_revision,
        addon_version=addon_version,
        addon_build_id=addon_build_id,
        profile_path_fingerprint=profile_path_fingerprint,
        features=tuple(features),
    )


@dataclass(frozen=True)
class McpRuntimeIdentity:
    runtime_id: str
    pid: int
    process_started_at: str
    hostname: str
    client_build_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "runtime_id", _require_uuid(self.runtime_id, "mcp.runtime_id"))
        _require_pid(self.pid, "mcp.pid")
        _parse_utc(self.process_started_at, "mcp.process_started_at")
        _require_identifier(self.hostname, "mcp.hostname")
        _require_identifier(self.client_build_id, "mcp.client_build_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_id": self.runtime_id,
            "pid": self.pid,
            "process_started_at": self.process_started_at,
            "hostname": self.hostname,
            "client_build_id": self.client_build_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "McpRuntimeIdentity":
        if not isinstance(payload, Mapping):
            raise LeaseProtocolError(
                "MALFORMED_HANDSHAKE", "MCP runtime identity must be an object"
            )
        _require_exact_keys(
            payload,
            required={
                "runtime_id",
                "pid",
                "process_started_at",
                "hostname",
                "client_build_id",
            },
            context="MCP runtime identity",
        )
        return cls(
            runtime_id=payload["runtime_id"],
            pid=payload["pid"],
            process_started_at=payload["process_started_at"],
            hostname=payload["hostname"],
            client_build_id=payload["client_build_id"],
        )


@dataclass(frozen=True)
class VerifiedHandshake:
    client_nonce: str
    mcp: McpRuntimeIdentity
    requested_features: tuple[str, ...]
    required_features: tuple[str, ...]


@dataclass(frozen=True)
class VerifiedHandshakeResponse:
    client_nonce: str
    server_nonce: str
    session_id: str
    session_token: str = field(repr=False)
    session_expires_at: str
    manifest: RuntimeManifest
    negotiated_features: tuple[str, ...]


def _normalize_features(value: Sequence[str], field_name: str) -> frozenset[str]:
    sequence = _require_sequence(value, field_name)
    if len(sequence) > 64:
        raise LeaseProtocolError(
            "MALFORMED_HANDSHAKE", f"{field_name} contains too many entries"
        )
    result: set[str] = set()
    for feature in sequence:
        result.add(_require_identifier(feature, field_name))
    return frozenset(result)


def _proof(secret: bytes, domain: bytes, payload: Mapping[str, Any]) -> str:
    digest = hmac.new(
        _validate_secret(secret), domain + canonical_json_bytes(dict(payload)), hashlib.sha256
    ).hexdigest()
    return f"{HMAC_ALGORITHM}:{digest}"


def _verify_proof(
    secret: bytes,
    domain: bytes,
    payload_without_proof: Mapping[str, Any],
    presented: Any,
) -> None:
    if not isinstance(presented, str) or not _PROOF_RE.fullmatch(presented):
        raise LeaseProtocolError(
            "AUTHENTICATION_FAILED", "Handshake authentication failed"
        )
    expected = _proof(secret, domain, payload_without_proof)
    if not hmac.compare_digest(expected, presented):
        raise LeaseProtocolError(
            "AUTHENTICATION_FAILED", "Handshake authentication failed"
        )


def sign_handshake_request(
    payload: Mapping[str, Any], secret: bytes
) -> dict[str, Any]:
    """Return a copy of a handshake request with a fresh request proof."""

    unsigned = dict(payload)
    unsigned.pop("proof", None)
    _limited_canonical_json(unsigned, MAX_HANDSHAKE_BYTES, "HANDSHAKE_TOO_LARGE")
    signed = copy.deepcopy(unsigned)
    signed["proof"] = _proof(secret, _REQUEST_PROOF_DOMAIN, unsigned)
    return signed


def build_handshake_request(
    *,
    secret: bytes,
    mcp: McpRuntimeIdentity,
    expected_profile_id: str,
    expected_freecad_pid: int,
    expected_freecad_process_started_at: str,
    expected_addon_runtime_id: str,
    expected_boot_id: str,
    expected_rpc_host: str,
    expected_rpc_port: int,
    expected_protocol_version: int,
    expected_protocol_features: Sequence[str],
    expected_addon_version: str,
    expected_addon_build_id: str,
    expected_freecad_version: str,
    expected_freecad_revision: str,
    expected_profile_path_fingerprint: str,
    requested_features: Sequence[str] = SUPPORTED_FEATURES,
    required_features: Sequence[str] = tuple(REQUIRED_PROTOCOL_FEATURES),
    client_nonce: str | None = None,
) -> dict[str, Any]:
    protocol_features = _normalize_features(
        tuple(expected_protocol_features), "expected.protocol_features"
    )
    if expected_protocol_version != PROTOCOL_VERSION:
        raise LeaseProtocolError(
            "UNSUPPORTED_PROTOCOL", "Expected RPC protocol version is unsupported"
        )
    expected: dict[str, Any] = {
        "profile_id": _require_identifier(expected_profile_id, "expected.profile_id"),
        "freecad_pid": _require_pid(expected_freecad_pid, "expected.freecad_pid"),
        "freecad_process_started_at": _format_utc(
            _parse_utc(
                expected_freecad_process_started_at,
                "expected.freecad_process_started_at",
            )
        ),
        "addon_runtime_id": _require_uuid(
            expected_addon_runtime_id, "expected.addon_runtime_id"
        ),
        "boot_id": _require_identifier(expected_boot_id, "expected.boot_id"),
        "rpc_host": _require_host(expected_rpc_host),
        "rpc_port": _require_port(expected_rpc_port),
        "protocol_version": expected_protocol_version,
        "features": sorted(protocol_features),
        "addon_version": _require_string(
            expected_addon_version, "expected.addon_version", maximum=256
        ),
        "addon_build_id": _require_identifier(
            expected_addon_build_id, "expected.addon_build_id"
        ),
        "freecad_version": _require_string(
            expected_freecad_version, "expected.freecad_version", maximum=256
        ),
        "freecad_revision": _require_string(
            expected_freecad_revision, "expected.freecad_revision", maximum=256
        ),
        "profile_path_fingerprint": _require_identifier(
            expected_profile_path_fingerprint,
            "expected.profile_path_fingerprint",
        ),
    }
    requested = _normalize_features(tuple(requested_features), "requested_features")
    required = _normalize_features(tuple(required_features), "required_features")
    if not required.issubset(requested):
        raise LeaseProtocolError(
            "MISSING_PROTOCOL_FEATURE",
            "Required features must also be requested",
        )
    request = {
        "kind": HANDSHAKE_REQUEST_KIND,
        "protocol_version": PROTOCOL_VERSION,
        "client_nonce": _validate_nonce(
            client_nonce or secrets.token_urlsafe(32), "client_nonce"
        ),
        "mcp": mcp.to_dict(),
        "expected_server": expected,
        "requested_features": sorted(requested),
        "required_features": sorted(required),
    }
    return sign_handshake_request(request, secret)


def verify_handshake_request(
    payload: Mapping[str, Any],
    *,
    secret: bytes,
    manifest: RuntimeManifest,
) -> VerifiedHandshake:
    if not isinstance(payload, Mapping):
        raise LeaseProtocolError(
            "MALFORMED_HANDSHAKE", "Handshake request must be an object"
        )
    _limited_canonical_json(dict(payload), MAX_HANDSHAKE_BYTES, "HANDSHAKE_TOO_LARGE")
    _require_exact_keys(
        payload,
        required={
            "kind",
            "protocol_version",
            "client_nonce",
            "mcp",
            "expected_server",
            "requested_features",
            "required_features",
            "proof",
        },
        context="handshake request",
    )
    unsigned = dict(payload)
    presented_proof = unsigned.pop("proof")
    _verify_proof(secret, _REQUEST_PROOF_DOMAIN, unsigned, presented_proof)
    if payload["kind"] != HANDSHAKE_REQUEST_KIND or payload["protocol_version"] != PROTOCOL_VERSION:
        raise LeaseProtocolError(
            "UNSUPPORTED_PROTOCOL", "Requested RPC protocol version is unsupported"
        )
    client_nonce = _validate_nonce(payload["client_nonce"], "client_nonce")
    mcp = McpRuntimeIdentity.from_dict(payload["mcp"])
    expected = payload["expected_server"]
    if not isinstance(expected, Mapping):
        raise LeaseProtocolError(
            "MALFORMED_HANDSHAKE", "Expected server identity must be an object"
        )
    _require_exact_keys(
        expected,
        required={
            "profile_id",
            "freecad_pid",
            "freecad_process_started_at",
            "addon_runtime_id",
            "boot_id",
            "rpc_host",
            "rpc_port",
            "protocol_version",
            "features",
            "addon_version",
            "addon_build_id",
            "freecad_version",
            "freecad_revision",
            "profile_path_fingerprint",
        },
        context="expected server identity",
    )
    expected_features = _normalize_features(
        expected["features"], "expected.features"
    )
    mismatch = (
        expected["profile_id"] != manifest.profile_id
        or expected["freecad_pid"] != manifest.freecad_pid
        or _format_utc(
            _parse_utc(
                expected["freecad_process_started_at"],
                "expected.freecad_process_started_at",
            )
        )
        != _format_utc(
            _parse_utc(
                manifest.freecad_process_started_at,
                "manifest.freecad_process_started_at",
            )
        )
        or expected["addon_runtime_id"] != manifest.addon_runtime_id
        or expected["boot_id"] != manifest.boot_id
        or expected["rpc_host"] != manifest.rpc_host
        or expected["rpc_port"] != manifest.rpc_port
        or expected["protocol_version"] != manifest.protocol_version
        or expected_features != frozenset(manifest.features)
        or expected["addon_version"] != manifest.addon_version
        or expected["addon_build_id"] != manifest.addon_build_id
        or expected["freecad_version"] != manifest.freecad_version
        or expected["freecad_revision"] != manifest.freecad_revision
        or expected["profile_path_fingerprint"]
        != manifest.profile_path_fingerprint
    )
    if mismatch:
        raise LeaseProtocolError(
            "INSTANCE_MISMATCH",
            "Handshake reached a different FreeCAD runtime than expected",
        )
    requested = _normalize_features(payload["requested_features"], "requested_features")
    required = _normalize_features(payload["required_features"], "required_features")
    if not required.issubset(requested):
        raise LeaseProtocolError(
            "MISSING_PROTOCOL_FEATURE", "Handshake required features were not requested"
        )
    if not required.issubset(manifest.features):
        raise LeaseProtocolError(
            "MISSING_PROTOCOL_FEATURE", "FreeCAD runtime lacks a required RPC feature"
        )
    return VerifiedHandshake(
        client_nonce=client_nonce,
        mcp=mcp,
        requested_features=tuple(sorted(requested)),
        required_features=tuple(sorted(required)),
    )


def sign_handshake_response(
    payload: Mapping[str, Any], secret: bytes
) -> dict[str, Any]:
    unsigned = dict(payload)
    unsigned.pop("proof", None)
    _limited_canonical_json(unsigned, MAX_HANDSHAKE_BYTES, "HANDSHAKE_TOO_LARGE")
    signed = copy.deepcopy(unsigned)
    signed["proof"] = _proof(secret, _RESPONSE_PROOF_DOMAIN, unsigned)
    return signed


def verify_handshake_response(
    payload: Mapping[str, Any],
    *,
    secret: bytes,
    expected_client_nonce: str,
    expected_profile_id: str,
    expected_freecad_pid: int,
    expected_freecad_process_started_at: str,
    expected_addon_runtime_id: str,
    expected_boot_id: str,
    expected_rpc_host: str,
    expected_rpc_port: int,
    expected_protocol_version: int,
    expected_protocol_features: Sequence[str],
    expected_addon_version: str,
    expected_addon_build_id: str,
    expected_freecad_version: str,
    expected_freecad_revision: str,
    expected_profile_path_fingerprint: str,
    required_features: Sequence[str] = tuple(REQUIRED_PROTOCOL_FEATURES),
) -> VerifiedHandshakeResponse:
    if not isinstance(payload, Mapping):
        raise LeaseProtocolError(
            "MALFORMED_HANDSHAKE", "Handshake response must be an object"
        )
    _limited_canonical_json(dict(payload), MAX_HANDSHAKE_BYTES, "HANDSHAKE_TOO_LARGE")
    _require_exact_keys(
        payload,
        required={
            "kind",
            "protocol_version",
            "client_nonce",
            "server_nonce",
            "session_id",
            "session_token",
            "session_expires_at",
            "manifest",
            "negotiated_features",
            "proof",
        },
        context="handshake response",
    )
    unsigned = dict(payload)
    presented_proof = unsigned.pop("proof")
    _verify_proof(secret, _RESPONSE_PROOF_DOMAIN, unsigned, presented_proof)
    if payload["kind"] != HANDSHAKE_RESPONSE_KIND or payload["protocol_version"] != PROTOCOL_VERSION:
        raise LeaseProtocolError(
            "UNSUPPORTED_PROTOCOL", "Returned RPC protocol version is unsupported"
        )
    if not hmac.compare_digest(
        _validate_nonce(payload["client_nonce"], "client_nonce"),
        _validate_nonce(expected_client_nonce, "expected_client_nonce"),
    ):
        raise LeaseProtocolError(
            "NONCE_MISMATCH", "Handshake response does not match the client request"
        )
    server_nonce = _validate_nonce(payload["server_nonce"], "server_nonce")
    session_id = _require_uuid(payload["session_id"], "session_id")
    session_token = _validate_token(payload["session_token"], "session_token")
    session_expires_at = _format_utc(
        _parse_utc(payload["session_expires_at"], "session_expires_at")
    )
    manifest = RuntimeManifest.from_dict(payload["manifest"])
    expected_features = _normalize_features(
        tuple(expected_protocol_features), "expected_protocol_features"
    )
    mismatch = (
        manifest.profile_id != expected_profile_id
        or manifest.freecad_pid != expected_freecad_pid
        or manifest.freecad_process_started_at
        != _format_utc(
            _parse_utc(
                expected_freecad_process_started_at,
                "expected_freecad_process_started_at",
            )
        )
        or manifest.addon_runtime_id != expected_addon_runtime_id
        or manifest.boot_id != expected_boot_id
        or manifest.rpc_host != expected_rpc_host
        or manifest.rpc_port != expected_rpc_port
        or manifest.protocol_version != expected_protocol_version
        or frozenset(manifest.features) != expected_features
        or manifest.addon_version != expected_addon_version
        or manifest.addon_build_id != expected_addon_build_id
        or manifest.freecad_version != expected_freecad_version
        or manifest.freecad_revision != expected_freecad_revision
        or manifest.profile_path_fingerprint
        != expected_profile_path_fingerprint
    )
    if mismatch:
        raise LeaseProtocolError(
            "INSTANCE_MISMATCH",
            "Handshake response identifies a different FreeCAD runtime",
        )
    negotiated = _normalize_features(
        payload["negotiated_features"], "negotiated_features"
    )
    required = _normalize_features(tuple(required_features), "required_features")
    if not required.issubset(negotiated):
        raise LeaseProtocolError(
            "MISSING_PROTOCOL_FEATURE", "Handshake response lacks a required feature"
        )
    if not negotiated.issubset(manifest.features):
        raise LeaseProtocolError(
            "MALFORMED_HANDSHAKE", "Handshake response advertises unknown features"
        )
    return VerifiedHandshakeResponse(
        client_nonce=payload["client_nonce"],
        server_nonce=server_nonce,
        session_id=session_id,
        session_token=session_token,
        session_expires_at=session_expires_at,
        manifest=manifest,
        negotiated_features=tuple(sorted(negotiated)),
    )


def _validate_token(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not _TOKEN_RE.fullmatch(value):
        raise LeaseProtocolError(
            "INVALID_CREDENTIAL", f"{field_name} is not a valid credential"
        )
    return value


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class SessionContext:
    session_id: str
    mcp: McpRuntimeIdentity
    negotiated_features: tuple[str, ...]
    issued_at: str
    expires_at: str


@dataclass
class _SessionRecord:
    context: SessionContext
    token_digest: str
    expires_monotonic: float
    revoked: bool = False
    revocation_reason: str | None = None


class SessionManager:
    """Issue, validate, expire, and revoke runtime-bound bearer sessions."""

    def __init__(
        self,
        *,
        manifest: RuntimeManifest,
        secret: bytes,
        session_ttl_seconds: float = DEFAULT_SESSION_TTL_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
        utcnow: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if not 1 <= session_ttl_seconds <= MAX_SESSION_TTL_SECONDS:
            raise LeaseProtocolError(
                "INVALID_SESSION_TTL", "Session lifetime is outside the supported range"
            )
        self.manifest = manifest
        self._secret = _validate_secret(secret)
        self._session_ttl = float(session_ttl_seconds)
        self._monotonic = monotonic
        self._utcnow = utcnow
        self._sessions_by_digest: dict[str, _SessionRecord] = {}
        self._sessions_by_id: dict[str, _SessionRecord] = {}
        # A signed request nonce is single-use for the complete addon runtime,
        # not merely for one session TTL.  Otherwise a captured handshake could
        # resurrect a dead MCP runtime after the original session expires.
        self._seen_nonces: set[tuple[str, str]] = set()
        self._lock = threading.RLock()

    def perform_handshake(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        verified = verify_handshake_request(
            payload, secret=self._secret, manifest=self.manifest
        )
        now_mono = self._monotonic()
        with self._lock:
            self._prune_locked(now_mono)
            nonce_key = (verified.mcp.runtime_id, verified.client_nonce)
            if nonce_key in self._seen_nonces:
                raise LeaseProtocolError(
                    "HANDSHAKE_REPLAY", "Handshake nonce has already been used"
                )
            if len(self._seen_nonces) >= MAX_HANDSHAKE_NONCES:
                raise LeaseProtocolError(
                    "HANDSHAKE_REPLAY_CACHE_FULL",
                    "Handshake nonce capacity is exhausted for this FreeCAD runtime",
                )
            self._seen_nonces.add(nonce_key)

            token = secrets.token_urlsafe(32)
            session_id = str(uuid.uuid4())
            issued_dt = self._utcnow()
            if issued_dt.tzinfo is None:
                raise LeaseProtocolError(
                    "INVALID_TIMESTAMP", "Session clock must include a timezone"
                )
            issued_dt = issued_dt.astimezone(timezone.utc)
            expires_dt = issued_dt + timedelta(seconds=self._session_ttl)
            negotiated = tuple(
                sorted(set(verified.requested_features).intersection(self.manifest.features))
            )
            context = SessionContext(
                session_id=session_id,
                mcp=verified.mcp,
                negotiated_features=negotiated,
                issued_at=_format_utc(issued_dt),
                expires_at=_format_utc(expires_dt),
            )
            record = _SessionRecord(
                context=context,
                token_digest=_token_digest(token),
                expires_monotonic=now_mono + self._session_ttl,
            )
            self._sessions_by_digest[record.token_digest] = record
            self._sessions_by_id[session_id] = record

        response = {
            "kind": HANDSHAKE_RESPONSE_KIND,
            "protocol_version": PROTOCOL_VERSION,
            "client_nonce": verified.client_nonce,
            "server_nonce": secrets.token_urlsafe(32),
            "session_id": session_id,
            "session_token": token,
            "session_expires_at": context.expires_at,
            "manifest": self.manifest.to_dict(),
            "negotiated_features": list(negotiated),
        }
        return sign_handshake_response(response, self._secret)

    def authenticate(self, session_token: str, *, mcp_runtime_id: str) -> SessionContext:
        token = _validate_token(session_token, "session_token")
        runtime_id = _require_uuid(mcp_runtime_id, "mcp_runtime_id")
        digest = _token_digest(token)
        now_mono = self._monotonic()
        with self._lock:
            record = self._sessions_by_digest.get(digest)
            if record is None or not hmac.compare_digest(record.token_digest, digest):
                raise LeaseProtocolError(
                    "INVALID_SESSION", "RPC session is invalid or no longer available"
                )
            if record.revoked:
                raise LeaseProtocolError(
                    "SESSION_REVOKED", "RPC session has been revoked"
                )
            if now_mono >= record.expires_monotonic:
                raise LeaseProtocolError("SESSION_EXPIRED", "RPC session has expired")
            if not hmac.compare_digest(record.context.mcp.runtime_id, runtime_id):
                raise LeaseProtocolError(
                    "SESSION_BINDING_MISMATCH",
                    "RPC session belongs to a different MCP runtime",
                )
            return record.context

    def authenticate_envelope(
        self,
        payload: Mapping[str, Any] | "RequestEnvelope",
        *,
        transport_mcp_runtime_id: str | None = None,
    ) -> tuple[SessionContext, "RequestEnvelope"]:
        envelope = (
            payload if isinstance(payload, RequestEnvelope) else RequestEnvelope.from_dict(payload)
        )
        if (
            transport_mcp_runtime_id is not None
            and envelope.mcp_runtime_id is not None
            and _require_uuid(transport_mcp_runtime_id, "transport_mcp_runtime_id")
            != envelope.mcp_runtime_id
        ):
            raise LeaseProtocolError(
                "SESSION_BINDING_MISMATCH",
                "Transport and request identify different MCP runtimes",
            )
        runtime_id = transport_mcp_runtime_id or envelope.mcp_runtime_id
        if runtime_id is None:
            raise LeaseProtocolError(
                "MISSING_RUNTIME_BINDING",
                "Authenticated requests must identify the MCP runtime",
            )
        context = self.authenticate(
            envelope.session_token, mcp_runtime_id=runtime_id
        )
        return context, envelope

    def revoke(
        self,
        *,
        session_id: str | None = None,
        session_token: str | None = None,
        reason: str = "revoked",
    ) -> bool:
        if (session_id is None) == (session_token is None):
            raise LeaseProtocolError(
                "INVALID_REVOCATION",
                "Exactly one session identifier is required for revocation",
            )
        with self._lock:
            if session_id is not None:
                record = self._sessions_by_id.get(_require_uuid(session_id, "session_id"))
            else:
                token = _validate_token(session_token, "session_token")
                record = self._sessions_by_digest.get(_token_digest(token))
            if record is None:
                return False
            record.revoked = True
            record.revocation_reason = _require_string(reason, "reason", maximum=128)
            return True

    def revoke_mcp_runtime(self, runtime_id: str, *, reason: str = "runtime revoked") -> int:
        normalized = _require_uuid(runtime_id, "mcp_runtime_id")
        count = 0
        with self._lock:
            for record in self._sessions_by_id.values():
                if record.context.mcp.runtime_id == normalized and not record.revoked:
                    record.revoked = True
                    record.revocation_reason = _require_string(reason, "reason", maximum=128)
                    count += 1
        return count

    def prune_expired(self) -> int:
        with self._lock:
            return self._prune_locked(self._monotonic())

    def _prune_locked(self, now_mono: float) -> int:
        expired_ids = [
            session_id
            for session_id, record in self._sessions_by_id.items()
            if now_mono >= record.expires_monotonic
        ]
        for session_id in expired_ids:
            record = self._sessions_by_id.pop(session_id)
            self._sessions_by_digest.pop(record.token_digest, None)
        return len(expired_ids)


@dataclass(frozen=True)
class LeaseCredential:
    lease_id: str
    document_session_uuid: str
    generation: int
    token: str = field(repr=False)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LeaseCredential":
        if not isinstance(payload, Mapping):
            raise LeaseProtocolError(
                "MALFORMED_LEASE_CREDENTIAL", "Lease credential must be an object"
            )
        _require_exact_keys(
            payload,
            required={"lease_id", "document_session_uuid", "generation", "token"},
            context="lease credential",
        )
        generation = payload["generation"]
        if (
            isinstance(generation, bool)
            or not isinstance(generation, int)
            or not 1 <= generation <= (2**63 - 1)
        ):
            raise LeaseProtocolError(
                "INVALID_LEASE_GENERATION",
                "Lease credential generation must be a positive integer",
            )
        return cls(
            lease_id=_require_uuid(payload["lease_id"], "lease_id"),
            document_session_uuid=_require_uuid(
                payload["document_session_uuid"], "document_session_uuid"
            ),
            generation=generation,
            token=_validate_token(payload["token"], "lease token"),
        )

    def redacted_dict(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "document_session_uuid": self.document_session_uuid,
            "generation": self.generation,
            "token": _REDACTED,
        }


@dataclass(frozen=True)
class OperationContext:
    name: str
    task_id: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "OperationContext":
        if not isinstance(payload, Mapping):
            raise LeaseProtocolError(
                "MALFORMED_ENVELOPE", "Operation metadata must be an object"
            )
        _require_exact_keys(
            payload,
            required={"name"},
            optional={"task_id"},
            context="operation metadata",
        )
        task_id = payload.get("task_id")
        return cls(
            name=_require_string(payload["name"], "operation.name", maximum=256),
            task_id=None if task_id is None else _require_uuid(task_id, "operation.task_id"),
        )


@dataclass(frozen=True)
class RequestEnvelope:
    request_id: str
    session_token: str = field(repr=False)
    method: str = ""
    params: dict[str, Any] = field(default_factory=dict, repr=False)
    lease_credentials: tuple[LeaseCredential, ...] = ()
    operation: OperationContext | None = None
    mcp_runtime_id: str | None = None
    protocol_version: int = PROTOCOL_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RequestEnvelope":
        if not isinstance(payload, Mapping):
            raise LeaseProtocolError(
                "MALFORMED_ENVELOPE", "Authenticated RPC envelope must be an object"
            )
        _limited_canonical_json(dict(payload), MAX_ENVELOPE_BYTES, "ENVELOPE_TOO_LARGE")
        _require_exact_keys(
            payload,
            required={
                "protocol_version",
                "request_id",
                "session_token",
                "method",
                "params",
                "lease_credentials",
            },
            optional={"operation", "mcp_runtime_id"},
            context="authenticated RPC envelope",
        )
        if payload["protocol_version"] != PROTOCOL_VERSION:
            raise LeaseProtocolError(
                "UNSUPPORTED_PROTOCOL", "Authenticated RPC protocol version is unsupported"
            )
        method = payload["method"]
        if not isinstance(method, str) or not _METHOD_RE.fullmatch(method):
            raise LeaseProtocolError(
                "INVALID_METHOD", "Authenticated RPC method name is invalid"
            )
        params = payload["params"]
        if not isinstance(params, dict):
            raise LeaseProtocolError(
                "MALFORMED_ENVELOPE", "Authenticated RPC params must be an object"
            )
        credentials_payload = _require_sequence(
            payload["lease_credentials"], "lease_credentials"
        )
        if len(credentials_payload) > MAX_LEASE_CREDENTIALS:
            raise LeaseProtocolError(
                "TOO_MANY_LEASES", "Authenticated RPC request declares too many leases"
            )
        credentials = tuple(
            LeaseCredential.from_dict(item) for item in credentials_payload
        )
        lease_ids = {credential.lease_id for credential in credentials}
        document_ids = {
            credential.document_session_uuid for credential in credentials
        }
        if len(lease_ids) != len(credentials) or len(document_ids) != len(credentials):
            raise LeaseProtocolError(
                "DUPLICATE_LEASE", "Authenticated RPC request repeats a lease or document"
            )
        operation_payload = payload.get("operation")
        mcp_runtime_id = payload.get("mcp_runtime_id")
        return cls(
            protocol_version=PROTOCOL_VERSION,
            request_id=_require_uuid(payload["request_id"], "request_id"),
            session_token=_validate_token(payload["session_token"], "session_token"),
            method=method,
            params=copy.deepcopy(params),
            lease_credentials=credentials,
            operation=None
            if operation_payload is None
            else OperationContext.from_dict(operation_payload),
            mcp_runtime_id=None
            if mcp_runtime_id is None
            else _require_uuid(mcp_runtime_id, "mcp_runtime_id"),
        )

    def semantic_fingerprint(self) -> str:
        """Fingerprint stable request semantics without renewable session data.

        Session tokens rotate during a normal authenticated reconnect.  The
        generated-operation capability signature is derived from that token,
        so it is likewise transport/session data rather than operation
        semantics.  The RPC boundary validates that signature against the
        current session *before* consulting the replay journal.
        """

        params = copy.deepcopy(self.params)
        if self.method == "execute_code":
            options = params.get("options")
            if isinstance(options, dict) and options.get("generated_operation"):
                options.pop("operation_signature", None)
        payload = {
            "protocol_version": self.protocol_version,
            "request_id": self.request_id,
            "mcp_runtime_id": self.mcp_runtime_id,
            "method": self.method,
            "params": params,
            "lease_credentials": sorted(
                [
                {
                    "lease_id": item.lease_id,
                    "document_session_uuid": item.document_session_uuid,
                    "generation": item.generation,
                    "token_digest": _token_digest(item.token),
                }
                for item in self.lease_credentials
                ],
                key=lambda item: (
                    item["document_session_uuid"],
                    item["lease_id"],
                    item["generation"],
                ),
            ),
            "operation": None
            if self.operation is None
            else {"name": self.operation.name, "task_id": self.operation.task_id},
        }
        return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()

    def fingerprint(self) -> str:
        """Compatibility alias for the stable semantic fingerprint."""

        return self.semantic_fingerprint()

    def redacted_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "request_id": self.request_id,
            "session_token": _REDACTED,
            "mcp_runtime_id": self.mcp_runtime_id,
            "method": self.method,
            "params": redact_sensitive(self.params),
            "lease_credentials": [item.redacted_dict() for item in self.lease_credentials],
            "operation": None
            if self.operation is None
            else {"name": self.operation.name, "task_id": self.operation.task_id},
        }


@dataclass(frozen=True)
class ReplayCheck:
    status: str
    response: Any = None


@dataclass
class _ReplayEntry:
    fingerprint: str
    expires_at: float
    pin_to_owner_leases: bool = False
    process_pinned: bool = False
    state: str = "in_progress"
    response: Any = None
    response_compacted: bool = False


class RequestReplayCache:
    """Bounded process-lifetime idempotency journal for authenticated requests.

    Keys use the authenticated MCP runtime UUID, which remains stable across
    short-lived RPC sessions.  Lease-affecting entries can be pinned while the
    runtime owns unresolved document authority.  Pinned entries are compacted,
    never evicted; capacity exhaustion therefore rejects new work fail closed.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_REPLAY_TTL_SECONDS,
        max_entries: int = 4096,
        response_max_bytes: int = DEFAULT_REPLAY_RESPONSE_MAX_BYTES,
        monotonic: Callable[[], float] = time.monotonic,
        owner_has_unresolved_lease: Callable[[str], bool] | None = None,
    ) -> None:
        if ttl_seconds <= 0 or max_entries <= 0 or response_max_bytes <= 0:
            raise ValueError("Replay cache bounds must be positive")
        self._ttl = float(ttl_seconds)
        self._max_entries = int(max_entries)
        self._response_max_bytes = int(response_max_bytes)
        self._monotonic = monotonic
        self._owner_has_unresolved_lease = (
            owner_has_unresolved_lease or (lambda _runtime_id: False)
        )
        self._entries: dict[tuple[str, str], _ReplayEntry] = {}
        self._lock = threading.RLock()

    def set_owner_lease_predicate(
        self, predicate: Callable[[str], bool]
    ) -> None:
        """Bind the process journal to the current lease authority service."""

        if not callable(predicate):
            raise TypeError("owner lease predicate must be callable")
        with self._lock:
            self._owner_has_unresolved_lease = predicate

    @staticmethod
    def _key(mcp_runtime_id: str, request_id: str) -> tuple[str, str]:
        return (
            _require_uuid(mcp_runtime_id, "mcp_runtime_id"),
            _require_uuid(request_id, "request_id"),
        )

    def claim(
        self,
        mcp_runtime_id: str,
        envelope: RequestEnvelope,
        *,
        pin_to_owner_leases: bool = False,
    ) -> ReplayCheck:
        key = self._key(mcp_runtime_id, envelope.request_id)
        fingerprint = envelope.semantic_fingerprint()
        now = self._monotonic()
        with self._lock:
            self._prune_locked(now)
            existing = self._entries.get(key)
            if existing is not None:
                if not hmac.compare_digest(existing.fingerprint, fingerprint):
                    raise LeaseProtocolError(
                        "REQUEST_ID_REUSE",
                        "Request ID was reused with different request content",
                    )
                return ReplayCheck(
                    existing.state,
                    copy.deepcopy(existing.response)
                    if existing.state == "completed"
                    else None,
                )
            self._ensure_capacity_locked()
            self._entries[key] = _ReplayEntry(
                fingerprint=fingerprint,
                expires_at=now + self._ttl,
                pin_to_owner_leases=bool(pin_to_owner_leases),
            )
            return ReplayCheck("new")

    def complete(
        self,
        mcp_runtime_id: str,
        envelope: RequestEnvelope,
        response: Any,
        *,
        process_pinned: bool = False,
    ) -> None:
        key = self._key(mcp_runtime_id, envelope.request_id)
        fingerprint = envelope.semantic_fingerprint()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or not hmac.compare_digest(entry.fingerprint, fingerprint):
                raise LeaseProtocolError(
                    "REQUEST_NOT_CLAIMED",
                    "Request must be claimed before its result is cached",
                )
            entry.state = "completed"
            entry.response = self._bounded_response(
                envelope.request_id,
                response,
                secrets=(
                    envelope.session_token,
                    *(item.token for item in envelope.lease_credentials),
                ),
            )
            entry.process_pinned = bool(entry.process_pinned or process_pinned)
            entry.response_compacted = self._is_completion_tombstone(entry.response)
            entry.expires_at = self._monotonic() + self._ttl

    def status(self, mcp_runtime_id: str, request_id: str) -> ReplayCheck:
        """Return request state for the authenticated owning MCP runtime."""

        key = self._key(mcp_runtime_id, request_id)
        now = self._monotonic()
        with self._lock:
            self._prune_locked(now)
            entry = self._entries.get(key)
            if entry is None:
                return ReplayCheck("unknown")
            return ReplayCheck(
                entry.state,
                copy.deepcopy(entry.response)
                if entry.state == "completed"
                else None,
            )

    def journal_completion(
        self,
        mcp_runtime_id: str,
        request_id: str,
        response: Any,
        *,
        secrets: Sequence[str] = (),
        process_pinned: bool = False,
    ) -> bool:
        """Replace a claimed request result after a late GUI completion.

        The callback is installed only by the authenticated dispatcher that
        already claimed this session/request pair.  It therefore does not need
        to retain a second copy of the (potentially secret-bearing) envelope.
        """

        key = self._key(mcp_runtime_id, request_id)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False
            entry.state = "completed"
            entry.response = self._bounded_response(
                key[1], response, secrets=tuple(secrets)
            )
            entry.process_pinned = bool(entry.process_pinned or process_pinned)
            entry.response_compacted = self._is_completion_tombstone(entry.response)
            entry.expires_at = self._monotonic() + self._ttl
            return True

    def abandon(self, mcp_runtime_id: str, envelope: RequestEnvelope) -> None:
        """Remove a claim only when its caller proved no side effect began."""

        key = self._key(mcp_runtime_id, envelope.request_id)
        fingerprint = envelope.semantic_fingerprint()
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and hmac.compare_digest(entry.fingerprint, fingerprint):
                self._entries.pop(key, None)

    def prune(self) -> int:
        with self._lock:
            return self._prune_locked(self._monotonic())

    def _prune_locked(self, now: float) -> int:
        removed = 0
        for key, entry in list(self._entries.items()):
            if entry.expires_at > now or entry.state == "in_progress":
                continue
            if self._entry_is_pinned_locked(key, entry):
                if not entry.response_compacted:
                    entry.response = self._completion_tombstone(key[1])
                    entry.response_compacted = True
                continue
            self._entries.pop(key, None)
            removed += 1
        return removed

    def _entry_is_pinned_locked(
        self, key: tuple[str, str], entry: _ReplayEntry
    ) -> bool:
        if entry.process_pinned:
            return True
        if not entry.pin_to_owner_leases:
            return False
        try:
            return bool(self._owner_has_unresolved_lease(key[0]))
        except Exception:
            # Losing visibility into lease authority must reduce availability,
            # never permit a duplicate document mutation.
            return True

    def _ensure_capacity_locked(self) -> None:
        if len(self._entries) < self._max_entries:
            return
        completed = [
            (entry.expires_at, key)
            for key, entry in self._entries.items()
            if entry.state == "completed"
            and not self._entry_is_pinned_locked(key, entry)
        ]
        if completed:
            _, oldest_key = min(completed)
            self._entries.pop(oldest_key, None)
            return
        raise LeaseProtocolError(
            "REPLAY_JOURNAL_FULL",
            "Authenticated request journal is full while protected entries remain",
        )

    @staticmethod
    def _scrub_exact_secrets(value: Any, secrets: Sequence[str]) -> Any:
        normalized = tuple(
            secret for secret in (str(item) for item in secrets) if secret
        )
        if isinstance(value, Mapping):
            return {
                str(key): RequestReplayCache._scrub_exact_secrets(item, normalized)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [
                RequestReplayCache._scrub_exact_secrets(item, normalized)
                for item in value
            ]
        if isinstance(value, str):
            result = value
            for secret in normalized:
                result = result.replace(secret, _REDACTED)
            return result
        return copy.deepcopy(value)

    def _bounded_response(
        self, request_id: str, response: Any, *, secrets: Sequence[str]
    ) -> Any:
        safe = redact_sensitive(self._scrub_exact_secrets(response, secrets))
        try:
            encoded = canonical_json_bytes(safe)
        except LeaseProtocolError:
            return self._completion_tombstone(request_id)
        if len(encoded) > self._response_max_bytes:
            return self._completion_tombstone(request_id)
        return safe

    @staticmethod
    def _completion_tombstone(request_id: str) -> dict[str, Any]:
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

    @staticmethod
    def _is_completion_tombstone(response: Any) -> bool:
        return bool(
            isinstance(response, Mapping)
            and isinstance(response.get("error"), Mapping)
            and response["error"].get("code") == "REQUEST_ALREADY_COMPLETED"
        )
