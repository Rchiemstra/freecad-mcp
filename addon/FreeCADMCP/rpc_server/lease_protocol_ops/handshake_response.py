"""Compatibility imports for canonical handshake-response operations."""

from __future__ import annotations

try:
    from ..._shared.protocol.handshake_response import (
        sign_handshake_response,
        verify_handshake_response,
    )
except ImportError:
    from _shared.protocol.handshake_response import (
        sign_handshake_response,
        verify_handshake_response,
    )

__all__ = ["sign_handshake_response", "verify_handshake_response"]
