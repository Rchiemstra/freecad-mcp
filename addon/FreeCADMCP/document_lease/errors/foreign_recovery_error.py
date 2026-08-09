"""Raised when a persisted foreign record could not be imported or fenced safely."""

from __future__ import annotations

from .local_recovery_error import LocalRecoveryError


class ForeignRecoveryError(LocalRecoveryError):
    """A persisted foreign record could not be imported or fenced safely."""

    __module__ = "document_lease.service"

    code = "FOREIGN_RECOVERY_UNSAFE"
