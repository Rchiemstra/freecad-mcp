"""Compatibility imports for canonical lease-protocol value types."""

try:
    from ..._shared.protocol.lease_credential import LeaseCredential
    from ..._shared.protocol.mcp_runtime_identity import McpRuntimeIdentity
    from ..._shared.protocol.operation_context import OperationContext
    from ..._shared.protocol.protocol_error import ProtocolError as LeaseProtocolError
    from ..._shared.protocol.replay_check import ReplayCheck
    from ..._shared.protocol.request_envelope import RequestEnvelope
    from ..._shared.protocol.runtime_manifest import RuntimeManifest
    from ..._shared.protocol.session_context import SessionContext
    from ..._shared.protocol.verified_handshake import VerifiedHandshake
    from ..._shared.protocol.verified_handshake_response import (
        VerifiedHandshakeResponse,
    )
except ImportError:
    from _shared.protocol.lease_credential import LeaseCredential
    from _shared.protocol.mcp_runtime_identity import McpRuntimeIdentity
    from _shared.protocol.operation_context import OperationContext
    from _shared.protocol.protocol_error import ProtocolError as LeaseProtocolError
    from _shared.protocol.replay_check import ReplayCheck
    from _shared.protocol.request_envelope import RequestEnvelope
    from _shared.protocol.runtime_manifest import RuntimeManifest
    from _shared.protocol.session_context import SessionContext
    from _shared.protocol.verified_handshake import VerifiedHandshake
    from _shared.protocol.verified_handshake_response import VerifiedHandshakeResponse

__all__ = [
    "LeaseCredential",
    "LeaseProtocolError",
    "McpRuntimeIdentity",
    "OperationContext",
    "ReplayCheck",
    "RequestEnvelope",
    "RuntimeManifest",
    "SessionContext",
    "VerifiedHandshake",
    "VerifiedHandshakeResponse",
]
