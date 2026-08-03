"""Compatibility imports for canonical handshake-request operations."""

from __future__ import annotations

try:
    from ..._shared.protocol.handshake_request import (
        build_handshake_request,
        sign_handshake_request,
        verify_handshake_request,
    )
except ImportError:
    from _shared.protocol.handshake_request import (
        build_handshake_request,
        sign_handshake_request,
        verify_handshake_request,
    )

__all__ = [
    "build_handshake_request",
    "sign_handshake_request",
    "verify_handshake_request",
]
