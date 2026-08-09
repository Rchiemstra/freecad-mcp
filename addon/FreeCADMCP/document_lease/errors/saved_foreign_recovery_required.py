"""Raised when a saved local-recovery sidecar needs off-GUI verification."""

from __future__ import annotations

from .foreign_recovery_error import ForeignRecoveryError


class SavedForeignRecoveryRequired(ForeignRecoveryError):
    """A saved local-recovery sidecar needs off-GUI verification and fencing."""

    __module__ = "document_lease.service"

    code = "SAVED_FOREIGN_RECOVERY_REQUIRED"
