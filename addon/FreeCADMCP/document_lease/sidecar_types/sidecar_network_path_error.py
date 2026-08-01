"""Raised when sidecar persistence is attempted on a network path."""

from __future__ import annotations

from .sidecar_error import SidecarError


class SidecarNetworkPathError(SidecarError):
    __module__ = "document_lease.sidecar"
