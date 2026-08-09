"""An explicit but dynamically composed public surface must fail closed."""

NAMES = tuple(f"Symbol{index}" for index in range(17))

__all__ = tuple(NAMES)
