"""P11: `Sketcher.Constraint` constructor signatures are inconsistent.

`DistanceX` should accept both the 1-point form `(geo, value)` and the 2-point
form `(geo1, pos1, geo2, pos2, value)`; `Coincident` is `(geo1, pos1, geo2,
pos2)`; `Radius` is `(geo, value)`. The 1-point `DistanceX` form historically
failed silently or errored. This test asserts the documented signatures all
construct without error.
"""
from __future__ import annotations

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")
Sketcher = pytest.importorskip("Sketcher")

pytestmark = [
    pytest.mark.core,
    pytest.mark.xfail(
        strict=True,
        reason="FreeCAD: Sketcher.Constraint DistanceX 1-point form inconsistent (P11)",
    ),
]


def test_distance_x_one_point_form(freecad_session):
    doc = freecad_session.doc
    body = doc.addObject("PartDesign::Body", "B")
    sk = body.newObject("Sketcher::SketchObject", "S")
    sk.addGeometry(Part.LineSegment(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(10, 0, 0)), False)
    doc.recompute()
    # 1-point DistanceX form: (geo, value).
    c = Sketcher.Constraint("DistanceX", 0, 5.0)
    sk.addConstraint(c)
    doc.recompute()
    assert any(getattr(con, "Name", "") == "DistanceX" for con in sk.Constraints), (
        "1-point DistanceX constraint was not added"
    )


def test_radius_and_coincident_forms(freecad_session):
    doc = freecad_session.doc
    body = doc.addObject("PartDesign::Body", "B2")
    sk = body.newObject("Sketcher::SketchObject", "S2")
    sk.addGeometry(Part.Circle(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 2), False)
    sk.addGeometry(Part.LineSegment(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(10, 0, 0)), False)
    doc.recompute()
    # Radius: (geo, value).
    sk.addConstraint(Sketcher.Constraint("Radius", 0, 2.0))
    # Coincident: (geo1, pos1, geo2, pos2) -- line start (1, 1) with circle centre (0, 3).
    sk.addConstraint(Sketcher.Constraint("Coincident", 1, 1, 0, 3))
    doc.recompute()
    names = {getattr(con, "Name", "") for con in sk.Constraints}
    assert {"Radius", "Coincident"} <= names, f"missing constraints; got {names}"
