"""InstanceMismatchError — extracted from lease_manager."""

from __future__ import annotations


class InstanceMismatchError(RuntimeError):
    """Raised when the FreeCAD addon on a port is not the expected instance."""
