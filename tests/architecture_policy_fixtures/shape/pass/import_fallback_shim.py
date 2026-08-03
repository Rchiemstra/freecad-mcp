"""Import-only compatibility shim for two package layouts."""

try:
    from canonical.value import Value as Value
except ImportError:
    from installed.value import Value as Value

__all__ = ("Value",)
