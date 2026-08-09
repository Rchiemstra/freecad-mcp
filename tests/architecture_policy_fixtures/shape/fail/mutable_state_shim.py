"""Compatibility shim with forbidden module-owned mutable state."""

from defining_module import TimeoutPolicy

__all__ = ("TimeoutPolicy",)

CACHE = []
