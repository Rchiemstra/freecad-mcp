"""Geometry checks for sketch constraints that FreeCAD only reports afterwards."""

from __future__ import annotations

_CIRCULAR_TYPES = frozenset({"Part::GeomCircle", "Part::GeomArcOfCircle"})


def circular_geometry_error(sketch: object, geo: int, constraint: str) -> str | None:
    """Why *constraint* cannot apply to geometry *geo*, or None when it can.

    FreeCAD adds a Radius or Diameter to any geometry and only its next solve
    reports the constraint as malformed. Axes and external geometry (negative
    indices) are left to FreeCAD.
    """

    geometry = getattr(sketch, "Geometry", None)
    if geo < 0 or not isinstance(geometry, (list, tuple)) or geo >= len(geometry):
        return None
    type_id = getattr(geometry[geo], "TypeId", None)
    if not isinstance(type_id, str) or type_id in _CIRCULAR_TYPES:
        return None
    return f"{constraint} needs a circle or arc, but geometry {geo} is a {type_id}"


__all__ = ["circular_geometry_error"]
