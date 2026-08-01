"""LeaseManagerClosedError — extracted from lease_manager."""

from __future__ import annotations

from .lease_manager_disconnected_error import LeaseManagerDisconnectedError


class LeaseManagerClosedError(LeaseManagerDisconnectedError):
    """Raised when work attempts to revive a terminally closed manager."""
