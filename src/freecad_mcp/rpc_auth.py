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

from .rpc_auth_ops.handshake_request import (
    build_handshake_request,
    build_handshake_request_from_manifest,
)
from .rpc_auth_ops.handshake_response import (
    verify_handshake_response,
    verify_handshake_response_from_manifest,
)
from .rpc_auth_ops.manifest import load_instance_manifest, make_mcp_runtime_identity

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
from .rpc_auth_types.profile_secret import load_profile_secret
from .rpc_auth_types.rpc_auth_error import RpcAuthError
from .rpc_auth_types.runtime_manifest import RuntimeManifest
from .rpc_auth_types.validation import canonical_json_bytes
from .rpc_auth_types.verified_handshake_response import VerifiedHandshakeResponse

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
