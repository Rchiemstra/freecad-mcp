"""A nested import-time mutation makes an explicit surface unauditable."""

A = object()
B = object()
ENABLED = True

__all__ = ("A",)

if ENABLED:
    __all__.append("B")
