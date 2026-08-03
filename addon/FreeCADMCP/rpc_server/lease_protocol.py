"""Compatibility facade for the canonical authenticated lease protocol."""

from __future__ import annotations

try:
    from .._shared.protocol.constants import (
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
    from .._shared.protocol.handshake_request import (
        build_handshake_request,
        sign_handshake_request,
        verify_handshake_request,
    )
    from .._shared.protocol.handshake_response import (
        sign_handshake_response,
        verify_handshake_response,
    )
    from .._shared.protocol.lease_credential import LeaseCredential
    from .._shared.protocol.manifest import make_runtime_manifest
    from .._shared.protocol.mcp_runtime_identity import McpRuntimeIdentity
    from .._shared.protocol.operation_context import OperationContext
    from .._shared.protocol.profile_secret import (
        create_profile_secret,
        load_profile_secret,
    )
    from .._shared.protocol.protocol_error import ProtocolError as LeaseProtocolError
    from .._shared.protocol.public_error import public_error
    from .._shared.protocol.redaction import redact_sensitive
    from .._shared.protocol.replay_check import ReplayCheck
    from .._shared.protocol.request_envelope import RequestEnvelope
    from .._shared.protocol.request_replay_cache import RequestReplayCache
    from .._shared.protocol.runtime_manifest import RuntimeManifest
    from .._shared.protocol.session_context import SessionContext
    from .._shared.protocol.session_manager import SessionManager
    from .._shared.protocol.validation import canonical_json_bytes
    from .._shared.protocol.verified_handshake import VerifiedHandshake
    from .._shared.protocol.verified_handshake_response import VerifiedHandshakeResponse
except ImportError:
    from _shared.protocol.constants import (  # noqa: F401
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
    from _shared.protocol.handshake_request import (
        build_handshake_request,
        sign_handshake_request,
        verify_handshake_request,
    )
    from _shared.protocol.handshake_response import (
        sign_handshake_response,
        verify_handshake_response,
    )
    from _shared.protocol.lease_credential import LeaseCredential
    from _shared.protocol.manifest import make_runtime_manifest
    from _shared.protocol.mcp_runtime_identity import McpRuntimeIdentity
    from _shared.protocol.operation_context import OperationContext
    from _shared.protocol.profile_secret import (
        create_profile_secret,
        load_profile_secret,
    )
    from _shared.protocol.protocol_error import ProtocolError as LeaseProtocolError
    from _shared.protocol.public_error import public_error
    from _shared.protocol.redaction import redact_sensitive
    from _shared.protocol.replay_check import ReplayCheck
    from _shared.protocol.request_envelope import RequestEnvelope
    from _shared.protocol.request_replay_cache import RequestReplayCache
    from _shared.protocol.runtime_manifest import RuntimeManifest
    from _shared.protocol.session_context import SessionContext
    from _shared.protocol.session_manager import SessionManager
    from _shared.protocol.validation import canonical_json_bytes
    from _shared.protocol.verified_handshake import VerifiedHandshake
    from _shared.protocol.verified_handshake_response import VerifiedHandshakeResponse

lease_protocol_public_error = public_error

__all__ = [
    "DEFAULT_REPLAY_RESPONSE_MAX_BYTES",
    "DEFAULT_REPLAY_TTL_SECONDS",
    "DEFAULT_SESSION_TTL_SECONDS",
    "HANDSHAKE_REQUEST_KIND",
    "HANDSHAKE_RESPONSE_KIND",
    "HMAC_ALGORITHM",
    "MAX_ENVELOPE_BYTES",
    "MAX_HANDSHAKE_BYTES",
    "MAX_HANDSHAKE_NONCES",
    "MAX_LEASE_CREDENTIALS",
    "MAX_PARAMS_DEPTH",
    "MAX_SECRET_FILE_BYTES",
    "MAX_SESSION_TTL_SECONDS",
    "MIN_SECRET_BYTES",
    "PROTOCOL_NAME",
    "PROTOCOL_VERSION",
    "REQUIRED_PROTOCOL_FEATURES",
    "SUPPORTED_FEATURES",
    "LeaseCredential",
    "LeaseProtocolError",
    "McpRuntimeIdentity",
    "OperationContext",
    "ReplayCheck",
    "RequestEnvelope",
    "RequestReplayCache",
    "RuntimeManifest",
    "SessionContext",
    "SessionManager",
    "VerifiedHandshake",
    "VerifiedHandshakeResponse",
    "build_handshake_request",
    "canonical_json_bytes",
    "create_profile_secret",
    "lease_protocol_public_error",
    "load_profile_secret",
    "make_runtime_manifest",
    "public_error",
    "redact_sensitive",
    "sign_handshake_request",
    "sign_handshake_response",
    "verify_handshake_request",
    "verify_handshake_response",
]
