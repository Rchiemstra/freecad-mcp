"""Compatibility import for the canonical verified handshake."""

try:
    from ..._shared.protocol.verified_handshake import VerifiedHandshake
except ImportError:
    from _shared.protocol.verified_handshake import VerifiedHandshake

__all__ = ["VerifiedHandshake"]
