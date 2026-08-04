"""Compatibility import for the canonical in-flight request registry."""

try:
    from ...dispatch.inflight_request_registry import InflightRequestRegistry
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from dispatch.inflight_request_registry import InflightRequestRegistry

__all__ = ["InflightRequestRegistry"]
