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

import contextlib
import copy
import hmac
import os
import secrets
import stat
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

# §3.3 compatibility shims — keep old import paths working.
from .lease_protocol_types.constants import (  # noqa: F401
    _PROCESS_STARTED_AT,
    _REDACTED,
    _REQUEST_PROOF_DOMAIN,
    _RESPONSE_PROOF_DOMAIN,
    DEFAULT_REPLAY_RESPONSE_MAX_BYTES,
    DEFAULT_REPLAY_TTL_SECONDS,
    DEFAULT_SESSION_TTL_SECONDS,
    HANDSHAKE_REQUEST_KIND,
    HANDSHAKE_RESPONSE_KIND,
    HMAC_ALGORITHM,
    MAX_ENVELOPE_BYTES,
    MAX_HANDSHAKE_BYTES,
    MAX_HANDSHAKE_NONCES,
    MAX_LEASE_CREDENTIALS,
    MAX_PARAMS_DEPTH,
    MAX_SECRET_FILE_BYTES,
    MAX_SESSION_TTL_SECONDS,
    MIN_SECRET_BYTES,
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    REQUIRED_PROTOCOL_FEATURES,
    SUPPORTED_FEATURES,
)
from .lease_protocol_types.lease_credential import LeaseCredential  # noqa: F401
from .lease_protocol_types.lease_protocol_error import LeaseProtocolError
from .lease_protocol_types.mcp_runtime_identity import McpRuntimeIdentity
from .lease_protocol_types.operation_context import OperationContext  # noqa: F401
from .lease_protocol_types.proof import _proof, _verify_proof
from .lease_protocol_types.redaction import redact_sensitive  # noqa: F401
from .lease_protocol_types.replay_check import ReplayCheck  # noqa: F401
from .lease_protocol_types.request_envelope import RequestEnvelope  # noqa: F401
from .lease_protocol_types.runtime_manifest import RuntimeManifest
from .lease_protocol_types.session_context import SessionContext  # noqa: F401
from .lease_protocol_types.validation import (
    _format_utc,
    _is_uuid,
    _limited_canonical_json,
    _normalize_features,
    _parse_utc,
    _require_exact_keys,
    _require_host,
    _require_identifier,
    _require_pid,
    _require_port,
    _require_string,
    _require_uuid,
    _validate_nonce,
    _validate_secret,
    _validate_token,
    canonical_json_bytes,  # noqa: F401
)
from .lease_protocol_types.verified_handshake import VerifiedHandshake
from .lease_protocol_types.verified_handshake_response import VerifiedHandshakeResponse


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
        with contextlib.suppress(OSError):
            target.unlink()
        raise
    return value


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
    if (
        payload["kind"] != HANDSHAKE_RESPONSE_KIND
        or payload["protocol_version"] != PROTOCOL_VERSION
    ):
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


# SessionManager imports handshake helpers from this module; defer shims until EOF
# so lease_protocol finishes initializing before the circular edge is resolved.
from .lease_protocol_types.request_replay_cache import RequestReplayCache  # noqa: E402, F401
from .lease_protocol_types.session_manager import SessionManager  # noqa: E402, F401
