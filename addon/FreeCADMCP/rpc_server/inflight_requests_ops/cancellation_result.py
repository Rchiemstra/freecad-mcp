"""Compatibility import for the canonical cancellation result."""

try:
    from ...dispatch.cancellation_result import CancellationResult
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from dispatch.cancellation_result import CancellationResult

__all__ = ["CancellationResult"]
