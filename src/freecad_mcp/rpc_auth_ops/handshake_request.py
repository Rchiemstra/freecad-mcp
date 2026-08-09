"""Compatibility exports for canonical handshake request operations."""

from __future__ import annotations

from .._shared.protocol.handshake_request import (
    build_handshake_request,
    build_handshake_request_from_manifest,
)

__all__ = [
    "build_handshake_request",
    "build_handshake_request_from_manifest",
]
