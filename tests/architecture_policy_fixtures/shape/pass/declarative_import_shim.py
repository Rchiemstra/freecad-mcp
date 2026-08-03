"""Compatibility spelling for :mod:`defining_module`; import-only by design."""

from defining_module import DEFAULT_TIMEOUT, TimeoutPolicy

__all__ = ("DEFAULT_TIMEOUT", "TimeoutPolicy")

DEPRECATION = {"replacement": "defining_module", "removal_phase": "later"}
