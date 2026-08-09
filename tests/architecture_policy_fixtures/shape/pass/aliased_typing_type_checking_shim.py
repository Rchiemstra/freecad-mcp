"""Import-only compatibility shim with an aliased typing guard."""

import typing as t

from defining_module import TimeoutPolicy as TimeoutPolicy

__all__ = ("TimeoutPolicy",)

if t.TYPE_CHECKING:
    pass
