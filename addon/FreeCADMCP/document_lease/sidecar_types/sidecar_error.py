"""Base error for guarded sidecar persistence."""

from __future__ import annotations


class SidecarError(RuntimeError):
    __module__ = "document_lease.sidecar"
