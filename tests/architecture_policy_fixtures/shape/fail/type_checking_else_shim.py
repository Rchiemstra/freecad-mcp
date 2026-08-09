"""Compatibility shim whose TYPE_CHECKING else branch mutates a registry."""

from typing import TYPE_CHECKING

from defining_module import TimeoutPolicy as TimeoutPolicy
from registry import register

__all__ = ("TimeoutPolicy",)

if TYPE_CHECKING:
    pass
else:
    register(TimeoutPolicy)
