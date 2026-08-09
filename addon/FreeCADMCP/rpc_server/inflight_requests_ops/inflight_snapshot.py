"""Compatibility import for the canonical in-flight request snapshot."""

try:
    from ...dispatch.inflight_snapshot import InflightSnapshot
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from dispatch.inflight_snapshot import InflightSnapshot

__all__ = ["InflightSnapshot"]
