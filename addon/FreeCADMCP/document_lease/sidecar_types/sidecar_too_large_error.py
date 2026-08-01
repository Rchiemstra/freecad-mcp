"""Raised when sidecar payload exceeds the configured byte limit."""

from __future__ import annotations

from .sidecar_malformed_error import SidecarMalformedError


class SidecarTooLargeError(SidecarMalformedError):
    __module__ = "document_lease.sidecar"
