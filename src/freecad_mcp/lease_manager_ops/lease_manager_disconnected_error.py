"""LeaseManagerDisconnectedError — extracted from lease_manager."""

from __future__ import annotations

from .lease_manager_error import LeaseManagerError


class LeaseManagerDisconnectedError(LeaseManagerError):
    """Raised when wire work is requested after the manager disconnected."""
