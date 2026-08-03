"""Compatibility import for canonical public protocol errors."""

from __future__ import annotations

try:
    from ..._shared.protocol.public_error import public_error
except ImportError:
    from _shared.protocol.public_error import public_error

__all__ = ["public_error"]
