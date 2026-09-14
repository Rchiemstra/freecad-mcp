"""Typed snapshot/restore operations."""
from __future__ import annotations

from .parametric_ops.restore import restore_operation
from .parametric_ops.snapshot import snapshot_operation

__all__ = ["restore_operation", "snapshot_operation"]
