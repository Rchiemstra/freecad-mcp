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

from .lease_protocol_ops.handshake_request import (
    build_handshake_request,
    sign_handshake_request,
    verify_handshake_request,
)
from .lease_protocol_ops.handshake_response import (
    sign_handshake_response,
    verify_handshake_response,
)
from .lease_protocol_ops.manifest import make_runtime_manifest
from .lease_protocol_ops.profile_secret import create_profile_secret, load_profile_secret
from .lease_protocol_ops.public_error import public_error

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
from .lease_protocol_types.lease_credential import LeaseCredential
from .lease_protocol_types.lease_protocol_error import LeaseProtocolError
from .lease_protocol_types.mcp_runtime_identity import McpRuntimeIdentity
from .lease_protocol_types.operation_context import OperationContext
from .lease_protocol_types.redaction import redact_sensitive
from .lease_protocol_types.replay_check import ReplayCheck
from .lease_protocol_types.request_envelope import RequestEnvelope
from .lease_protocol_types.request_replay_cache import RequestReplayCache
from .lease_protocol_types.runtime_manifest import RuntimeManifest
from .lease_protocol_types.session_context import SessionContext
from .lease_protocol_types.session_manager import SessionManager
from .lease_protocol_types.validation import (
    canonical_json_bytes,
)
from .lease_protocol_types.verified_handshake import VerifiedHandshake
from .lease_protocol_types.verified_handshake_response import VerifiedHandshakeResponse

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
    "load_profile_secret",
    "make_runtime_manifest",
    "public_error",
    "redact_sensitive",
    "sign_handshake_request",
    "sign_handshake_response",
    "verify_handshake_request",
    "verify_handshake_response",
]
