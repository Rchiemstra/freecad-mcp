"""Compatibility facade for the canonical authenticated RPC protocol."""

from __future__ import annotations

from ._shared.protocol.constants import (  # noqa: F401
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
from ._shared.protocol.handshake_request import (
    build_handshake_request,
    build_handshake_request_from_manifest,
)
from ._shared.protocol.handshake_response import (
    verify_handshake_response,
    verify_handshake_response_from_manifest,
)
from ._shared.protocol.instance_manifest import InstanceManifest
from ._shared.protocol.manifest import (
    load_instance_manifest,
    make_mcp_runtime_identity,
)
from ._shared.protocol.mcp_runtime_identity import McpRuntimeIdentity
from ._shared.protocol.profile_secret import load_profile_secret
from ._shared.protocol.protocol_error import ProtocolError as RpcAuthError
from ._shared.protocol.runtime_manifest import RuntimeManifest
from ._shared.protocol.validation import canonical_json_bytes
from ._shared.protocol.verified_handshake_response import VerifiedHandshakeResponse

__all__ = [
    "HANDSHAKE_REQUEST_KIND",
    "HANDSHAKE_RESPONSE_KIND",
    "HMAC_ALGORITHM",
    "INSTANCE_MANIFEST_SCHEMA_VERSION",
    "MAX_ACCEPTED_SESSION_LIFETIME_SECONDS",
    "MAX_HANDSHAKE_BYTES",
    "MAX_INSTANCE_MANIFEST_BYTES",
    "MAX_JSON_DEPTH",
    "MAX_SECRET_FILE_BYTES",
    "MIN_SECRET_BYTES",
    "PROTOCOL_NAME",
    "PROTOCOL_VERSION",
    "REQUIRED_PROTOCOL_FEATURES",
    "SUPPORTED_FEATURES",
    "InstanceManifest",
    "McpRuntimeIdentity",
    "RpcAuthError",
    "RuntimeManifest",
    "VerifiedHandshakeResponse",
    "build_handshake_request",
    "build_handshake_request_from_manifest",
    "canonical_json_bytes",
    "load_instance_manifest",
    "load_profile_secret",
    "make_mcp_runtime_identity",
    "verify_handshake_response",
    "verify_handshake_response_from_manifest",
]
