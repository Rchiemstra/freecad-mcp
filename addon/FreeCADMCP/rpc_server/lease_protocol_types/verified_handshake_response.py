"""Compatibility import for the canonical verified handshake response."""

try:
    from ..._shared.protocol.verified_handshake_response import (
        VerifiedHandshakeResponse,
    )
except ImportError:
    from _shared.protocol.verified_handshake_response import VerifiedHandshakeResponse

__all__ = ["VerifiedHandshakeResponse"]
