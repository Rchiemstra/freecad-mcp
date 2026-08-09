"""Compatibility import for the canonical cancellation token."""

try:
    from ...dispatch.cancellation_token import CancellationToken
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from dispatch.cancellation_token import CancellationToken

__all__ = ["CancellationToken"]
