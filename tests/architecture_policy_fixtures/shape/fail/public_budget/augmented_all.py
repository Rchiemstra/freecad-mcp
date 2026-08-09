"""Mutation after a literal public surface must remain auditable."""

Symbol16 = object()

__all__ = tuple(f"Symbol{index}" for index in range(16))
__all__ += ("Symbol16",)
