"""Compatibility import for the canonical in-flight request."""

try:
    from ...dispatch.inflight_request import InflightRequest
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from dispatch.inflight_request import InflightRequest

__all__ = ["InflightRequest"]
