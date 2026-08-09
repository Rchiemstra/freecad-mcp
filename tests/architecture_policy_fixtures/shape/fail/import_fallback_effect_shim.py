"""Compatibility shim whose import fallback performs runtime work."""

try:
    from canonical.value import Value as Value
except ImportError:
    from registry import register

    register(Value)

__all__ = ("Value",)
