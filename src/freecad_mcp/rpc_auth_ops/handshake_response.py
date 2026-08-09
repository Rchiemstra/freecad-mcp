"""Compatibility exports for canonical handshake response operations."""

from __future__ import annotations

from .._shared.protocol.handshake_response import (
    verify_handshake_response,
    verify_handshake_response_from_manifest,
)

__all__ = [
    "verify_handshake_response",
    "verify_handshake_response_from_manifest",
]
