"""Sketcher geometry item builders (Phase 4 slice 4F)."""

from __future__ import annotations

import math


def _add_line(sketch, geom, construction, *, freecad, part):
    start, end = geom["start"], geom["end"]
    segment = part.LineSegment(
        freecad.Vector(start.get("x", 0), start.get("y", 0), 0),
        freecad.Vector(end.get("x", 0), end.get("y", 0), 0),
    )
    return [sketch.addGeometry(segment, construction)]


def _add_circle(sketch, geom, construction, *, freecad, part):
    center = geom.get("center", {"x": 0, "y": 0})
    circle = part.Circle(
        freecad.Vector(center.get("x", 0), center.get("y", 0), 0),
        freecad.Vector(0, 0, 1),
        geom.get("radius", 1),
    )
    return [sketch.addGeometry(circle, construction)]


def _add_arc(sketch, geom, construction, *, freecad, part):
    center = geom.get("center", {"x": 0, "y": 0})
    radius = geom.get("radius", 1)
    base_circle = part.Circle(
        freecad.Vector(center.get("x", 0), center.get("y", 0), 0),
        freecad.Vector(0, 0, 1),
        radius,
    )
    arc = part.ArcOfCircle(
        base_circle,
        math.radians(geom.get("start_angle", 0)),
        math.radians(geom.get("end_angle", 90)),
    )
    return [sketch.addGeometry(arc, construction)]


def _add_rectangle(sketch, geom, construction, *, freecad, part):
    x1, y1 = geom.get("x1", 0), geom.get("y1", 0)
    x2, y2 = geom.get("x2", 10), geom.get("y2", 10)
    corners = [
        (freecad.Vector(x1, y1, 0), freecad.Vector(x2, y1, 0)),
        (freecad.Vector(x2, y1, 0), freecad.Vector(x2, y2, 0)),
        (freecad.Vector(x2, y2, 0), freecad.Vector(x1, y2, 0)),
        (freecad.Vector(x1, y2, 0), freecad.Vector(x1, y1, 0)),
    ]
    return [
        sketch.addGeometry(part.LineSegment(p1, p2), construction) for p1, p2 in corners
    ]


def _add_point(sketch, geom, construction, *, freecad, part):
    point = part.Point(freecad.Vector(geom.get("x", 0), geom.get("y", 0), 0))
    return [sketch.addGeometry(point, construction)]


_GEOMETRY_BUILDERS = {
    "line": _add_line,
    "circle": _add_circle,
    "arc": _add_arc,
    "rectangle": _add_rectangle,
    "point": _add_point,
}


def add_sketch_geometry_item(
    sketch, geom, *, freecad, part
) -> tuple[list[int], str | None]:
    geom_type = geom.get("type", "").lower()
    builder = _GEOMETRY_BUILDERS.get(geom_type)
    if builder is None:
        return [], f"Unknown geometry type: '{geom_type}'"
    return builder(
        sketch, geom, geom.get("construction", False), freecad=freecad, part=part
    ), None
