"""Raised when a clean missing-sidecar record needs off-GUI verification."""

from __future__ import annotations

from .foreign_recovery_error import ForeignRecoveryError


class OrphanedForeignRecoveryRequired(ForeignRecoveryError):
    """A clean missing-sidecar record needs off-GUI verification."""

    __module__ = "document_lease.service"

    code = "ORPHANED_FOREIGN_RECOVERY_REQUIRED"
