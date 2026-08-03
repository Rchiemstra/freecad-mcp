"""Import-only compatibility shim with a qualified type-checking guard."""

import typing

from defining_module import TimeoutPolicy as TimeoutPolicy

__all__ = ("TimeoutPolicy",)

if typing.TYPE_CHECKING:
    pass
