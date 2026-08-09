"""Compatibility spelling for :mod:`defining_module`; import-only by design."""

# §3.3 compatibility shims — keep old import paths working.
from defining_module import DEFAULT_TIMEOUT, TimeoutPolicy

__all__ = ("DEFAULT_TIMEOUT", "TimeoutPolicy")

register(DEFAULT_TIMEOUT)
