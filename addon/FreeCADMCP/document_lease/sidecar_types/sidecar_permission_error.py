"""Raised when filesystem permissions or ACL checks fail."""

from __future__ import annotations

from .sidecar_error import SidecarError


class SidecarPermissionError(SidecarError):
    __module__ = "document_lease.sidecar"
