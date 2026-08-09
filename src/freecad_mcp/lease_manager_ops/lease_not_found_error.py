"""LeaseNotFoundError — extracted from lease_manager."""

from __future__ import annotations

from .lease_manager_error import LeaseManagerError


class LeaseNotFoundError(LeaseManagerError):
    """Raised when no credential matches a document selector."""
