"""Raised when compare-and-swap or existence preconditions fail."""

from __future__ import annotations

from .sidecar_error import SidecarError


class SidecarConflictError(SidecarError):
    __module__ = "document_lease.sidecar"
