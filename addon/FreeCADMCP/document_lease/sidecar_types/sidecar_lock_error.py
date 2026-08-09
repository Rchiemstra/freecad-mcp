"""Raised when advisory guard locking fails."""

from __future__ import annotations

from .sidecar_error import SidecarError


class SidecarLockError(SidecarError):
    __module__ = "document_lease.sidecar"
