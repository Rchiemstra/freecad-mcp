"""Standard-library client helpers for authenticated FreeCAD RPC protocol v2.

The addon has a matching implementation in
``addon.FreeCADMCP.rpc_server.lease_protocol``.  This module intentionally does
not import it: the MCP process and isolated-instance launchers must be able to
authenticate without importing FreeCAD addon code.

The profile secret and issued session token are credentials.  They are never
included in dataclass representations or exception details by this module.
The HMAC handshake authenticates the selected local runtime; it does not
encrypt XML-RPC traffic, so non-loopback transports still require TLS or an
encrypted tunnel.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import stat
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


PROTOCOL_NAME = "freecad-mcp-rpc"
PROTOCOL_VERSION = 2
HANDSHAKE_REQUEST_KIND = "freecad-mcp-handshake-v2"
HANDSHAKE_RESPONSE_KIND = "freecad-mcp-handshake-v2-response"
HMAC_ALGORITHM = "hmac-sha256"
INSTANCE_MANIFEST_SCHEMA_VERSION = 1

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

MAX_HANDSHAKE_BYTES = 64 * 1024
MAX_INSTANCE_MANIFEST_BYTES = 64 * 1024
MAX_SECRET_FILE_BYTES = 4096
MIN_SECRET_BYTES = 32
MAX_JSON_DEPTH = 32
MAX_ACCEPTED_SESSION_LIFETIME_SECONDS = 60 * 60 + 30

_PROCESS_STARTED_AT = datetime.now(timezone.utc)
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+\-=]{0,255}$")
_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{22,128}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,512}$")
_PROOF_RE = re.compile(r"^hmac-sha256:([0-9a-f]{64})$")
_REQUEST_PROOF_DOMAIN = b"freecad-mcp-rpc-v2\x00handshake-request\x00"
_RESPONSE_PROOF_DOMAIN = b"freecad-mcp-rpc-v2\x00handshake-response\x00"


class RpcAuthError(ValueError):
    """A bounded authentication failure with a stable public error code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = str(code)
        self.public_message = str(message)
        super().__init__(f"{self.code}: {self.public_message}")


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
    return parsed.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise RpcAuthError(
            "INVALID_TIMESTAMP", "Runtime timestamps must include a timezone"
        )
    return (
        value.astimezone(timezone.utc)
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


def _proof(secret: bytes, domain: bytes, payload: Mapping[str, Any]) -> str:
    digest = hmac.new(
        _validate_secret(secret),
        domain + canonical_json_bytes(dict(payload)),
        hashlib.sha256,
    ).hexdigest()
    return f"{HMAC_ALGORITHM}:{digest}"


def _verify_proof(
    secret: bytes,
    domain: bytes,
    payload_without_proof: Mapping[str, Any],
    presented: Any,
) -> None:
    if not isinstance(presented, str) or not _PROOF_RE.fullmatch(presented):
        raise RpcAuthError("AUTHENTICATION_FAILED", "Handshake authentication failed")
    expected = _proof(secret, domain, payload_without_proof)
    if not hmac.compare_digest(expected, presented):
        raise RpcAuthError("AUTHENTICATION_FAILED", "Handshake authentication failed")


def load_profile_secret(
    path: str | os.PathLike[str],
    *,
    require_owner_only: bool = True,
) -> bytes:
    """Load a bounded regular-file secret with the addon's safety checks."""

    secret_path = Path(path)
    try:
        before = secret_path.lstat()
    except OSError as exc:
        raise RpcAuthError(
            "PROFILE_SECRET_UNAVAILABLE", "Profile authentication secret is unavailable"
        ) from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RpcAuthError(
            "INSECURE_PROFILE_SECRET",
            "Profile authentication secret must be a regular file",
        )
    if not MIN_SECRET_BYTES <= before.st_size <= MAX_SECRET_FILE_BYTES:
        raise RpcAuthError(
            "INVALID_PROFILE_SECRET",
            "Profile authentication secret has an invalid size",
        )
    if require_owner_only and os.name != "nt":
        if before.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise RpcAuthError(
                "INSECURE_PROFILE_SECRET",
                "Profile authentication secret must be accessible only to its owner",
            )
        if hasattr(os, "geteuid") and before.st_uid != os.geteuid():
            raise RpcAuthError(
                "INSECURE_PROFILE_SECRET",
                "Profile authentication secret must be owned by the current user",
            )
    try:
        with secret_path.open("rb") as handle:
            value = handle.read(MAX_SECRET_FILE_BYTES + 1)
            after = os.fstat(handle.fileno())
    except OSError as exc:
        raise RpcAuthError(
            "PROFILE_SECRET_UNAVAILABLE", "Profile authentication secret is unavailable"
        ) from exc
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise RpcAuthError(
            "PROFILE_SECRET_CHANGED",
            "Profile authentication secret changed while loading",
        )
    return _validate_secret(value)


@dataclass(frozen=True)
class McpRuntimeIdentity:
    runtime_id: str
    pid: int
    process_started_at: str
    hostname: str
    client_build_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "runtime_id", _require_uuid(self.runtime_id, "mcp.runtime_id")
        )
        _require_pid(self.pid, "mcp.pid")
        object.__setattr__(
            self,
            "process_started_at",
            _format_utc(_parse_utc(self.process_started_at, "mcp.process_started_at")),
        )
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


def make_mcp_runtime_identity(
    *,
    client_build_id: str,
    runtime_id: str | None = None,
    pid: int | None = None,
    process_started_at: str | None = None,
    hostname: str | None = None,
) -> McpRuntimeIdentity:
    """Create the immutable identity used for one MCP process lifetime."""

    return McpRuntimeIdentity(
        runtime_id=runtime_id or str(uuid.uuid4()),
        pid=os.getpid() if pid is None else pid,
        process_started_at=process_started_at or _format_utc(_PROCESS_STARTED_AT),
        hostname=hostname or socket.gethostname(),
        client_build_id=client_build_id,
    )


@dataclass(frozen=True)
class InstanceManifest:
    """Persistent isolated-profile manifest plus optional launched-runtime facts."""

    rpc_host: str
    rpc_port: int
    profile_instance_id: str
    profile_path: str
    auth_secret_file: str = field(repr=False)
    expected_freecad_pid: int | None = None
    expected_freecad_process_started_at: str | None = None
    expected_addon_runtime_id: str | None = None
    expected_boot_id: str | None = None
    expected_protocol_version: int | None = None
    expected_protocol_features: tuple[str, ...] | None = None
    expected_addon_version: str | None = None
    expected_addon_build_id: str | None = None
    expected_freecad_version: str | None = None
    expected_freecad_revision: str | None = None
    expected_profile_path_fingerprint: str | None = None
    created_at: str = ""
    schema_version: int = INSTANCE_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != INSTANCE_MANIFEST_SCHEMA_VERSION:
            raise RpcAuthError(
                "UNSUPPORTED_INSTANCE_MANIFEST",
                "Instance manifest schema is unsupported",
            )
        _require_host(self.rpc_host)
        _require_port(self.rpc_port)
        _require_identifier(self.profile_instance_id, "profile_instance_id")
        _require_string(self.profile_path, "profile_path", maximum=4096)
        _require_string(self.auth_secret_file, "auth_secret_file", maximum=4096)
        if self.expected_freecad_pid is not None:
            _require_pid(self.expected_freecad_pid, "expected_freecad_pid")
        if self.expected_freecad_process_started_at is not None:
            object.__setattr__(
                self,
                "expected_freecad_process_started_at",
                _format_utc(
                    _parse_utc(
                        self.expected_freecad_process_started_at,
                        "expected_freecad_process_started_at",
                    )
                ),
            )
        if self.expected_addon_runtime_id is not None:
            object.__setattr__(
                self,
                "expected_addon_runtime_id",
                _require_uuid(
                    self.expected_addon_runtime_id, "expected_addon_runtime_id"
                ),
            )
        if self.expected_boot_id is not None:
            _require_identifier(self.expected_boot_id, "expected_boot_id")
        if self.expected_protocol_version is not None:
            if self.expected_protocol_version != PROTOCOL_VERSION:
                raise RpcAuthError(
                    "UNSUPPORTED_PROTOCOL",
                    "Instance manifest protocol version is unsupported",
                )
        if self.expected_protocol_features is not None:
            features = _normalize_features(
                self.expected_protocol_features, "expected_protocol_features"
            )
            if not REQUIRED_PROTOCOL_FEATURES.issubset(features):
                raise RpcAuthError(
                    "MISSING_PROTOCOL_FEATURE",
                    "Instance manifest omits a required protocol feature",
                )
            object.__setattr__(
                self, "expected_protocol_features", tuple(sorted(features))
            )
        if self.expected_addon_version is not None:
            _require_string(
                self.expected_addon_version, "expected_addon_version", maximum=256
            )
        if self.expected_addon_build_id is not None:
            _require_identifier(self.expected_addon_build_id, "expected_addon_build_id")
        if self.expected_freecad_version is not None:
            _require_string(
                self.expected_freecad_version, "expected_freecad_version", maximum=256
            )
        if self.expected_freecad_revision is not None:
            _require_string(
                self.expected_freecad_revision,
                "expected_freecad_revision",
                maximum=256,
            )
        if self.expected_profile_path_fingerprint is not None:
            _require_identifier(
                self.expected_profile_path_fingerprint,
                "expected_profile_path_fingerprint",
            )
        _format_utc(_parse_utc(self.created_at, "created_at"))

    def require_complete_runtime(self) -> None:
        """Reject a setup-only manifest before any authenticated connection."""

        required = {
            "expected_freecad_pid": self.expected_freecad_pid,
            "expected_freecad_process_started_at": (
                self.expected_freecad_process_started_at
            ),
            "expected_addon_runtime_id": self.expected_addon_runtime_id,
            "expected_boot_id": self.expected_boot_id,
            "expected_protocol_version": self.expected_protocol_version,
            "expected_protocol_features": self.expected_protocol_features,
            "expected_addon_version": self.expected_addon_version,
            "expected_addon_build_id": self.expected_addon_build_id,
            "expected_freecad_version": self.expected_freecad_version,
            "expected_freecad_revision": self.expected_freecad_revision,
            "expected_profile_path_fingerprint": (
                self.expected_profile_path_fingerprint
            ),
        }
        if any(value is None for value in required.values()):
            raise RpcAuthError(
                "INCOMPLETE_INSTANCE_MANIFEST",
                "Instance manifest does not contain an exact launched runtime identity",
            )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InstanceManifest":
        if not isinstance(payload, Mapping):
            raise RpcAuthError(
                "MALFORMED_INSTANCE_MANIFEST", "Instance manifest must be an object"
            )
        _require_exact_keys(
            payload,
            required={
                "schema_version",
                "rpc_host",
                "rpc_port",
                "profile_instance_id",
                "profile_path",
                "auth_secret_file",
                "expected_freecad_pid",
                "expected_freecad_process_started_at",
                "expected_addon_runtime_id",
                "expected_boot_id",
                "expected_protocol_version",
                "expected_protocol_features",
                "expected_addon_version",
                "expected_addon_build_id",
                "expected_freecad_version",
                "expected_freecad_revision",
                "expected_profile_path_fingerprint",
                "created_at",
            },
            context="instance manifest",
        )
        return cls(**dict(payload))

    def load_secret(self, *, require_owner_only: bool = True) -> bytes:
        return load_profile_secret(
            self.auth_secret_file, require_owner_only=require_owner_only
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "rpc_host": self.rpc_host,
            "rpc_port": self.rpc_port,
            "profile_instance_id": self.profile_instance_id,
            "profile_path": self.profile_path,
            "auth_secret_file": self.auth_secret_file,
            "expected_freecad_pid": self.expected_freecad_pid,
            "expected_freecad_process_started_at": (
                self.expected_freecad_process_started_at
            ),
            "expected_addon_runtime_id": self.expected_addon_runtime_id,
            "expected_boot_id": self.expected_boot_id,
            "expected_protocol_version": self.expected_protocol_version,
            "expected_protocol_features": (
                list(self.expected_protocol_features)
                if self.expected_protocol_features is not None
                else None
            ),
            "expected_addon_version": self.expected_addon_version,
            "expected_addon_build_id": self.expected_addon_build_id,
            "expected_freecad_version": self.expected_freecad_version,
            "expected_freecad_revision": self.expected_freecad_revision,
            "expected_profile_path_fingerprint": (
                self.expected_profile_path_fingerprint
            ),
            "created_at": self.created_at,
        }


def load_instance_manifest(path: str | os.PathLike[str]) -> InstanceManifest:
    """Read a stable, bounded instance manifest without following a link."""

    manifest_path = Path(path)
    try:
        before = manifest_path.lstat()
    except OSError as exc:
        raise RpcAuthError(
            "INSTANCE_MANIFEST_UNAVAILABLE", "Instance manifest is unavailable"
        ) from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RpcAuthError(
            "INSECURE_INSTANCE_MANIFEST", "Instance manifest must be a regular file"
        )
    if not 1 <= before.st_size <= MAX_INSTANCE_MANIFEST_BYTES:
        raise RpcAuthError(
            "MALFORMED_INSTANCE_MANIFEST", "Instance manifest has an invalid size"
        )
    try:
        with manifest_path.open("rb") as handle:
            raw = handle.read(MAX_INSTANCE_MANIFEST_BYTES + 1)
            after = os.fstat(handle.fileno())
    except OSError as exc:
        raise RpcAuthError(
            "INSTANCE_MANIFEST_UNAVAILABLE", "Instance manifest is unavailable"
        ) from exc
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise RpcAuthError(
            "INSTANCE_MANIFEST_CHANGED", "Instance manifest changed while loading"
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RpcAuthError(
            "MALFORMED_INSTANCE_MANIFEST", "Instance manifest must contain UTF-8 JSON"
        ) from exc
    _bounded_json(payload, MAX_INSTANCE_MANIFEST_BYTES, "MALFORMED_INSTANCE_MANIFEST")
    manifest = InstanceManifest.from_dict(payload)
    profile_path = Path(manifest.profile_path)
    secret_path = Path(manifest.auth_secret_file)
    if not profile_path.is_absolute() or not secret_path.is_absolute():
        raise RpcAuthError(
            "INSECURE_INSTANCE_MANIFEST",
            "Isolated profile and authentication paths must be absolute",
        )
    resolved_profile = profile_path.resolve()
    if manifest_path.resolve().parent != resolved_profile:
        raise RpcAuthError(
            "INSECURE_INSTANCE_MANIFEST",
            "Instance manifest must reside at the isolated profile root",
        )
    try:
        secret_path.resolve().relative_to(resolved_profile)
    except ValueError as exc:
        raise RpcAuthError(
            "INSECURE_INSTANCE_MANIFEST",
            "Authentication secret must remain inside the isolated profile",
        ) from exc
    return manifest


@dataclass(frozen=True)
class RuntimeManifest:
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
            self,
            "addon_runtime_id",
            _require_uuid(self.addon_runtime_id, "addon_runtime_id"),
        )
        _require_pid(self.freecad_pid, "freecad_pid")
        object.__setattr__(
            self,
            "freecad_process_started_at",
            _format_utc(
                _parse_utc(
                    self.freecad_process_started_at, "freecad_process_started_at"
                )
            ),
        )
        _require_identifier(self.boot_id, "boot_id")
        _require_host(self.rpc_host)
        _require_port(self.rpc_port)
        for name in (
            "freecad_version",
            "freecad_revision",
            "addon_version",
            "addon_build_id",
        ):
            _require_string(getattr(self, name), name, maximum=256)
        _require_identifier(self.profile_path_fingerprint, "profile_path_fingerprint")
        if self.protocol_version != PROTOCOL_VERSION:
            raise RpcAuthError(
                "UNSUPPORTED_PROTOCOL",
                "Runtime manifest protocol version is unsupported",
            )
        features = _normalize_features(self.features, "features")
        if not REQUIRED_PROTOCOL_FEATURES.issubset(features):
            raise RpcAuthError(
                "MISSING_PROTOCOL_FEATURE",
                "Runtime manifest omits a required protocol feature",
            )
        object.__setattr__(self, "features", tuple(sorted(features)))

    @property
    def endpoint(self) -> str:
        host = f"[{self.rpc_host}]" if ":" in self.rpc_host else self.rpc_host
        return f"{host}:{self.rpc_port}"

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimeManifest":
        if not isinstance(payload, Mapping):
            raise RpcAuthError(
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
            raise RpcAuthError(
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
            raise RpcAuthError(
                "INSTANCE_MISMATCH", "Runtime manifest endpoint is inconsistent"
            )
        return manifest


@dataclass(frozen=True)
class VerifiedHandshakeResponse:
    client_nonce: str
    server_nonce: str
    session_id: str
    session_token: str = field(repr=False)
    session_expires_at: str
    manifest: RuntimeManifest
    negotiated_features: tuple[str, ...]


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
    """Construct the exact signed request accepted by the addon protocol."""

    protocol_features = _normalize_features(
        tuple(expected_protocol_features), "expected.protocol_features"
    )
    if expected_protocol_version != PROTOCOL_VERSION:
        raise RpcAuthError(
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
        raise RpcAuthError(
            "MISSING_PROTOCOL_FEATURE", "Required features must also be requested"
        )
    unsigned = {
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
    _bounded_json(unsigned, MAX_HANDSHAKE_BYTES, "HANDSHAKE_TOO_LARGE")
    signed = copy.deepcopy(unsigned)
    signed["proof"] = _proof(secret, _REQUEST_PROOF_DOMAIN, unsigned)
    return signed


def build_handshake_request_from_manifest(
    *,
    secret: bytes,
    mcp: McpRuntimeIdentity,
    manifest: InstanceManifest,
    client_nonce: str | None = None,
    requested_features: Sequence[str] = SUPPORTED_FEATURES,
    required_features: Sequence[str] = tuple(REQUIRED_PROTOCOL_FEATURES),
) -> dict[str, Any]:
    """Build a request only after the launcher populated exact runtime facts."""

    manifest.require_complete_runtime()
    return build_handshake_request(
        secret=secret,
        mcp=mcp,
        expected_profile_id=manifest.profile_instance_id,
        expected_freecad_pid=manifest.expected_freecad_pid,
        expected_freecad_process_started_at=(
            manifest.expected_freecad_process_started_at
        ),
        expected_addon_runtime_id=manifest.expected_addon_runtime_id,
        expected_boot_id=manifest.expected_boot_id,
        expected_rpc_host=manifest.rpc_host,
        expected_rpc_port=manifest.rpc_port,
        expected_protocol_version=manifest.expected_protocol_version,
        expected_protocol_features=manifest.expected_protocol_features,
        expected_addon_version=manifest.expected_addon_version,
        expected_addon_build_id=manifest.expected_addon_build_id,
        expected_freecad_version=manifest.expected_freecad_version,
        expected_freecad_revision=manifest.expected_freecad_revision,
        expected_profile_path_fingerprint=(
            manifest.expected_profile_path_fingerprint
        ),
        requested_features=requested_features,
        required_features=required_features,
        client_nonce=client_nonce,
    )


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
    """Authenticate a response and prove it is the requested FreeCAD runtime."""

    if not isinstance(payload, Mapping):
        raise RpcAuthError(
            "MALFORMED_HANDSHAKE", "Handshake response must be an object"
        )
    _bounded_json(dict(payload), MAX_HANDSHAKE_BYTES, "HANDSHAKE_TOO_LARGE")
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
    if (
        payload["kind"] != HANDSHAKE_RESPONSE_KIND
        or payload["protocol_version"] != expected_protocol_version
        or expected_protocol_version != PROTOCOL_VERSION
    ):
        raise RpcAuthError(
            "UNSUPPORTED_PROTOCOL", "Returned RPC protocol version is unsupported"
        )
    actual_nonce = _validate_nonce(payload["client_nonce"], "client_nonce")
    wanted_nonce = _validate_nonce(expected_client_nonce, "expected_client_nonce")
    if not hmac.compare_digest(actual_nonce, wanted_nonce):
        raise RpcAuthError(
            "NONCE_MISMATCH", "Handshake response does not match the client request"
        )
    server_nonce = _validate_nonce(payload["server_nonce"], "server_nonce")
    session_id = _require_uuid(payload["session_id"], "session_id")
    session_token = _validate_token(payload["session_token"], "session_token")
    session_expiry = _parse_utc(payload["session_expires_at"], "session_expires_at")
    now = datetime.now(timezone.utc)
    if session_expiry <= now:
        raise RpcAuthError(
            "INVALID_SESSION_EXPIRY", "Handshake returned an expired RPC session"
        )
    if session_expiry > now + timedelta(seconds=MAX_ACCEPTED_SESSION_LIFETIME_SECONDS):
        raise RpcAuthError(
            "INVALID_SESSION_EXPIRY",
            "Handshake returned an unexpectedly long-lived RPC session",
        )
    session_expires_at = _format_utc(session_expiry)
    manifest = RuntimeManifest.from_dict(payload["manifest"])

    expected_start = _format_utc(
        _parse_utc(
            expected_freecad_process_started_at,
            "expected_freecad_process_started_at",
        )
    )
    expected_features = _normalize_features(
        tuple(expected_protocol_features), "expected_protocol_features"
    )
    mismatch = (
        manifest.profile_id
        != _require_identifier(expected_profile_id, "expected.profile_id")
        or manifest.freecad_pid
        != _require_pid(expected_freecad_pid, "expected.freecad_pid")
        or manifest.addon_runtime_id
        != _require_uuid(expected_addon_runtime_id, "expected.addon_runtime_id")
        or manifest.freecad_process_started_at != expected_start
        or manifest.boot_id != _require_identifier(expected_boot_id, "expected.boot_id")
        or manifest.rpc_host != _require_host(expected_rpc_host)
        or manifest.rpc_port != _require_port(expected_rpc_port)
        or manifest.protocol_version != expected_protocol_version
        or frozenset(manifest.features) != expected_features
        or manifest.addon_version
        != _require_string(expected_addon_version, "expected.addon_version", maximum=256)
        or manifest.addon_build_id
        != _require_identifier(expected_addon_build_id, "expected.addon_build_id")
        or manifest.freecad_version
        != _require_string(
            expected_freecad_version, "expected.freecad_version", maximum=256
        )
        or manifest.freecad_revision
        != _require_string(
            expected_freecad_revision, "expected.freecad_revision", maximum=256
        )
        or manifest.profile_path_fingerprint
        != _require_identifier(
            expected_profile_path_fingerprint,
            "expected.profile_path_fingerprint",
        )
    )
    if mismatch:
        raise RpcAuthError(
            "INSTANCE_MISMATCH",
            "Handshake response identifies a different FreeCAD runtime",
        )

    negotiated = _normalize_features(
        payload["negotiated_features"], "negotiated_features"
    )
    required = _normalize_features(tuple(required_features), "required_features")
    if not required.issubset(negotiated):
        raise RpcAuthError(
            "MISSING_PROTOCOL_FEATURE", "Handshake response lacks a required feature"
        )
    if not negotiated.issubset(manifest.features):
        raise RpcAuthError(
            "MALFORMED_HANDSHAKE", "Handshake response advertises unknown features"
        )
    return VerifiedHandshakeResponse(
        client_nonce=actual_nonce,
        server_nonce=server_nonce,
        session_id=session_id,
        session_token=session_token,
        session_expires_at=session_expires_at,
        manifest=manifest,
        negotiated_features=tuple(sorted(negotiated)),
    )


def verify_handshake_response_from_manifest(
    payload: Mapping[str, Any],
    *,
    secret: bytes,
    expected_client_nonce: str,
    manifest: InstanceManifest,
    required_features: Sequence[str] = tuple(REQUIRED_PROTOCOL_FEATURES),
) -> VerifiedHandshakeResponse:
    """Verify all runtime assertions stored in an isolated-instance manifest."""

    manifest.require_complete_runtime()
    return verify_handshake_response(
        payload,
        secret=secret,
        expected_client_nonce=expected_client_nonce,
        expected_profile_id=manifest.profile_instance_id,
        expected_freecad_pid=manifest.expected_freecad_pid,
        expected_freecad_process_started_at=manifest.expected_freecad_process_started_at,
        expected_addon_runtime_id=manifest.expected_addon_runtime_id,
        expected_boot_id=manifest.expected_boot_id,
        expected_rpc_host=manifest.rpc_host,
        expected_rpc_port=manifest.rpc_port,
        expected_protocol_version=manifest.expected_protocol_version,
        expected_protocol_features=manifest.expected_protocol_features,
        expected_addon_version=manifest.expected_addon_version,
        expected_addon_build_id=manifest.expected_addon_build_id,
        expected_freecad_version=manifest.expected_freecad_version,
        expected_freecad_revision=manifest.expected_freecad_revision,
        expected_profile_path_fingerprint=(
            manifest.expected_profile_path_fingerprint
        ),
        required_features=required_features,
    )
