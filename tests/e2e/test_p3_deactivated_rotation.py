"""P3: `MapMode = Deactivated` + a manually rotated Placement is ignored.

A `PartDesign::AdditiveCylinder` with `MapMode='Deactivated'` and
`Placement = rot(Y, 90deg)` (which maps the default Z axis onto +X) must
produce a cylinder whose axis is +X. FreeCAD silently keeps the default axis
and discards the rotation. Relates to FreeCAD #19571.
"""
from __future__ import annotations

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")

# First calibrated run against this branch's FreeCAD (1.2.0dev): the bug this
# test reproduces is fixed, so the strict xfail flipped to XPASS and failed the
# run. Keep the test as a plain regression gate against the bug returning.
pytestmark = [
    pytest.mark.core,
]


def test_deactivated_cylinder_honours_placement_rotation(freecad_session):
    doc = freecad_session.doc
    body = doc.addObject("PartDesign::Body", "CylBody")
    cyl = body.newObject("PartDesign::AdditiveCylinder", "Cyl")
    cyl.Radius = 2
    cyl.Height = 1
    cyl.Angle = 360
    cyl.MapMode = "Deactivated"
    # Rotate the default Z axis onto +X (90 deg about Y).
    cyl.Placement = FreeCAD.Placement(
        FreeCAD.Vector(0, 0, 0), FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), 90)
    )
    doc.recompute()

    bbox = cyl.Shape.BoundBox
    # Expected: cylinder axis +X, height 1 along X, radius 2 in Y/Z.
    assert abs(bbox.XMin - 0.0) <= 1e-3 and abs(bbox.XMax - 1.0) <= 1e-3, (
        f"cylinder X extent {bbox.XMin}..{bbox.XMax} != 0..1 (rotation dropped)"
    )
    assert abs(bbox.YMin - (-2.0)) <= 1e-3 and abs(bbox.YMax - 2.0) <= 1e-3
    assert abs(bbox.ZMin - (-2.0)) <= 1e-3 and abs(bbox.ZMax - 2.0) <= 1e-3
