"""Raised when sidecar bytes fail schema validation."""

from __future__ import annotations

from .sidecar_error import SidecarError


class SidecarMalformedError(SidecarError):
    __module__ = "document_lease.sidecar"
