"""Handshake request construction for authenticated RPC v2."""

from __future__ import annotations

import copy
import secrets
from collections.abc import Sequence
from typing import Any

from ..rpc_auth_types.constants import (
    _REQUEST_PROOF_DOMAIN,
    HANDSHAKE_REQUEST_KIND,
    MAX_HANDSHAKE_BYTES,
    PROTOCOL_VERSION,
    REQUIRED_PROTOCOL_FEATURES,
    SUPPORTED_FEATURES,
)
from ..rpc_auth_types.instance_manifest import InstanceManifest
from ..rpc_auth_types.mcp_runtime_identity import McpRuntimeIdentity
from ..rpc_auth_types.proof import _proof
from ..rpc_auth_types.rpc_auth_error import RpcAuthError
from ..rpc_auth_types.validation import (
    _bounded_json,
    _format_utc,
    _normalize_features,
    _parse_utc,
    _require_host,
    _require_identifier,
    _require_pid,
    _require_port,
    _require_string,
    _require_uuid,
    _validate_nonce,
)


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
