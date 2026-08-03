"""Import-only compatibility shim with an aliased TYPE_CHECKING guard."""

from typing import TYPE_CHECKING as TC

from defining_module import TimeoutPolicy as TimeoutPolicy

__all__ = ("TimeoutPolicy",)

if TC:
    pass
