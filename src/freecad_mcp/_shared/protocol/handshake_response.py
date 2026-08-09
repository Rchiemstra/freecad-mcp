"""Handshake response verification for authenticated RPC v2."""

from __future__ import annotations

import copy
import hmac
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from .constants import (
    _RESPONSE_PROOF_DOMAIN,
    HANDSHAKE_RESPONSE_KIND,
    MAX_ACCEPTED_SESSION_LIFETIME_SECONDS,
    MAX_HANDSHAKE_BYTES,
    PROTOCOL_VERSION,
    REQUIRED_PROTOCOL_FEATURES,
)
from .instance_manifest import InstanceManifest
from .proof import _proof, _verify_proof
from .protocol_error import ProtocolError
from .runtime_manifest import RuntimeManifest
from .validation import (
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
)
from .verified_handshake_response import VerifiedHandshakeResponse


def sign_handshake_response(
    payload: Mapping[str, Any], secret: bytes
) -> dict[str, Any]:
    """Return a copy of a response with one canonical HMAC proof."""

    unsigned = dict(payload)
    unsigned.pop("proof", None)
    _bounded_json(unsigned, MAX_HANDSHAKE_BYTES, "HANDSHAKE_TOO_LARGE")
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
    """Authenticate a response and prove it is the requested FreeCAD runtime."""

    if not isinstance(payload, Mapping):
        raise ProtocolError(
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
        raise ProtocolError(
            "UNSUPPORTED_PROTOCOL", "Returned RPC protocol version is unsupported"
        )
    actual_nonce = _validate_nonce(payload["client_nonce"], "client_nonce")
    wanted_nonce = _validate_nonce(expected_client_nonce, "expected_client_nonce")
    if not hmac.compare_digest(actual_nonce, wanted_nonce):
        raise ProtocolError(
            "NONCE_MISMATCH", "Handshake response does not match the client request"
        )
    server_nonce = _validate_nonce(payload["server_nonce"], "server_nonce")
    session_id = _require_uuid(payload["session_id"], "session_id")
    session_token = _validate_token(payload["session_token"], "session_token")
    session_expiry = _parse_utc(payload["session_expires_at"], "session_expires_at")
    now = datetime.now(UTC)
    if session_expiry <= now:
        raise ProtocolError(
            "INVALID_SESSION_EXPIRY", "Handshake returned an expired RPC session"
        )
    if session_expiry > now + timedelta(seconds=MAX_ACCEPTED_SESSION_LIFETIME_SECONDS):
        raise ProtocolError(
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
        raise ProtocolError(
            "INSTANCE_MISMATCH",
            "Handshake response identifies a different FreeCAD runtime",
        )

    negotiated = _normalize_features(
        payload["negotiated_features"], "negotiated_features"
    )
    required = _normalize_features(tuple(required_features), "required_features")
    if not required.issubset(negotiated):
        raise ProtocolError(
            "MISSING_PROTOCOL_FEATURE", "Handshake response lacks a required feature"
        )
    if not negotiated.issubset(manifest.features):
        raise ProtocolError(
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
