"""Compatibility exports for canonical RPC authentication types."""

from .._shared.protocol.instance_manifest import InstanceManifest
from .._shared.protocol.mcp_runtime_identity import McpRuntimeIdentity
from .._shared.protocol.protocol_error import ProtocolError as RpcAuthError
from .._shared.protocol.runtime_manifest import RuntimeManifest
from .._shared.protocol.verified_handshake_response import VerifiedHandshakeResponse

__all__ = [
    "InstanceManifest",
    "McpRuntimeIdentity",
    "RpcAuthError",
    "RuntimeManifest",
    "VerifiedHandshakeResponse",
]
