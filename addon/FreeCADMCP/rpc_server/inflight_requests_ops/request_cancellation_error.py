"""Compatibility import for the canonical cancellation error."""

try:
    from ...dispatch.request_cancellation_error import RequestCancellationError
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from dispatch.request_cancellation_error import RequestCancellationError

__all__ = ["RequestCancellationError"]
