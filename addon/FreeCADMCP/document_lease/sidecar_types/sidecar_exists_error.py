"""Raised when creating a sidecar that already exists."""

from __future__ import annotations

from .sidecar_error import SidecarError


class SidecarExistsError(SidecarError):
    __module__ = "document_lease.sidecar"
