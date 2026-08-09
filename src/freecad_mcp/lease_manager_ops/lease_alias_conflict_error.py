"""LeaseAliasConflictError — extracted from lease_manager."""

from __future__ import annotations

from .lease_manager_error import LeaseManagerError


class LeaseAliasConflictError(LeaseManagerError):
    """Raised when a canonical path is already owned by another document."""
