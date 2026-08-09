"""Raised when a sidecar file is missing."""

from __future__ import annotations

from .sidecar_error import SidecarError


class SidecarNotFoundError(SidecarError):
    __module__ = "document_lease.sidecar"
