"""Handshake response signing and verification."""

from __future__ import annotations

import copy
import hmac
from collections.abc import Mapping, Sequence
from typing import Any

from ..lease_protocol_types.constants import (
    _RESPONSE_PROOF_DOMAIN,
    HANDSHAKE_RESPONSE_KIND,
    MAX_HANDSHAKE_BYTES,
    PROTOCOL_VERSION,
    REQUIRED_PROTOCOL_FEATURES,
)
from ..lease_protocol_types.lease_protocol_error import LeaseProtocolError
from ..lease_protocol_types.proof import _proof, _verify_proof
from ..lease_protocol_types.runtime_manifest import RuntimeManifest
from ..lease_protocol_types.validation import (
    _format_utc,
    _limited_canonical_json,
    _normalize_features,
    _parse_utc,
    _require_exact_keys,
    _require_uuid,
    _validate_nonce,
    _validate_token,
)
from ..lease_protocol_types.verified_handshake_response import VerifiedHandshakeResponse


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
