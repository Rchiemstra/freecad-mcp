"""Handshake request signing, construction, and verification."""

from __future__ import annotations

import copy
import secrets
from collections.abc import Mapping, Sequence
from typing import Any

from .constants import (
    _REQUEST_PROOF_DOMAIN,
    HANDSHAKE_REQUEST_KIND,
    MAX_HANDSHAKE_BYTES,
    PROTOCOL_VERSION,
    REQUIRED_PROTOCOL_FEATURES,
    SUPPORTED_FEATURES,
)
from .instance_manifest import InstanceManifest
from .mcp_runtime_identity import McpRuntimeIdentity
from .proof import _proof, _verify_proof
from .protocol_error import ProtocolError
from .runtime_manifest import RuntimeManifest
from .validation import (
    _format_utc,
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
)
from .verified_handshake import VerifiedHandshake


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
        raise ProtocolError(
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
        raise ProtocolError(
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
        raise ProtocolError(
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
        raise ProtocolError(
            "UNSUPPORTED_PROTOCOL", "Requested RPC protocol version is unsupported"
        )
    client_nonce = _validate_nonce(payload["client_nonce"], "client_nonce")
    mcp = McpRuntimeIdentity.from_dict(payload["mcp"])
    expected = payload["expected_server"]
    if not isinstance(expected, Mapping):
        raise ProtocolError(
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
        raise ProtocolError(
            "INSTANCE_MISMATCH",
            "Handshake reached a different FreeCAD runtime than expected",
        )
    requested = _normalize_features(payload["requested_features"], "requested_features")
    required = _normalize_features(payload["required_features"], "required_features")
    if not required.issubset(requested):
        raise ProtocolError(
            "MISSING_PROTOCOL_FEATURE", "Handshake required features were not requested"
        )
    if not required.issubset(manifest.features):
        raise ProtocolError(
            "MISSING_PROTOCOL_FEATURE", "FreeCAD runtime lacks a required RPC feature"
        )
    return VerifiedHandshake(
        client_nonce=client_nonce,
        mcp=mcp,
        requested_features=tuple(sorted(requested)),
        required_features=tuple(sorted(required)),
    )


def build_handshake_request_from_manifest(
    *,
    secret: bytes,
    mcp: McpRuntimeIdentity,
    manifest: InstanceManifest,
    client_nonce: str | None = None,
    requested_features: Sequence[str] = SUPPORTED_FEATURES,
    required_features: Sequence[str] = tuple(REQUIRED_PROTOCOL_FEATURES),
) -> dict[str, Any]:
    """Build a request from a complete isolated-instance manifest."""

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
