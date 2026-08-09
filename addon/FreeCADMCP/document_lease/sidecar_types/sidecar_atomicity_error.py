"""Raised when an atomic filesystem operation cannot be completed safely."""

from __future__ import annotations

from .sidecar_error import SidecarError


class SidecarAtomicityError(SidecarError):
    __module__ = "document_lease.sidecar"
