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
import hmac
import json
import os
import secrets
import socket
import stat
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# §3.3 compatibility shims — keep old import paths working.
from .rpc_auth_types.constants import (  # noqa: F401
    _PROCESS_STARTED_AT,
    _REQUEST_PROOF_DOMAIN,
    _RESPONSE_PROOF_DOMAIN,
    HANDSHAKE_REQUEST_KIND,
    HANDSHAKE_RESPONSE_KIND,
    HMAC_ALGORITHM,
    INSTANCE_MANIFEST_SCHEMA_VERSION,
    MAX_ACCEPTED_SESSION_LIFETIME_SECONDS,
    MAX_HANDSHAKE_BYTES,
    MAX_INSTANCE_MANIFEST_BYTES,
    MAX_JSON_DEPTH,
    MAX_SECRET_FILE_BYTES,
    MIN_SECRET_BYTES,
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    REQUIRED_PROTOCOL_FEATURES,
    SUPPORTED_FEATURES,
)
from .rpc_auth_types.instance_manifest import InstanceManifest
from .rpc_auth_types.mcp_runtime_identity import McpRuntimeIdentity
from .rpc_auth_types.profile_secret import load_profile_secret  # noqa: F401
from .rpc_auth_types.proof import _proof, _verify_proof
from .rpc_auth_types.rpc_auth_error import RpcAuthError
from .rpc_auth_types.runtime_manifest import RuntimeManifest
from .rpc_auth_types.validation import (
    _bounded_json,
    _format_utc,
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
    _validate_token,
    canonical_json_bytes,  # noqa: F401
)
from .rpc_auth_types.verified_handshake_response import VerifiedHandshakeResponse


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
    now = datetime.now(UTC)
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
