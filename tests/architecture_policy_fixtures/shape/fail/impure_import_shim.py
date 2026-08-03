"""A shim-shaped module which must fail because import mutates state."""

from defining_module import TimeoutPolicy

__all__ = ("TimeoutPolicy",)

REGISTERED = []
REGISTERED.append(TimeoutPolicy)
