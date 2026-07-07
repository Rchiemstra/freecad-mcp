"""P4: shape-placement absorption defeats the snapshot workaround.

Baking a solid into global coordinates and assigning it to a `Part::Feature`
with `Placement = identity` should leave geometry-at-global with identity
placement. FreeCAD couples a shape's geometry to its Placement, so the
placement is absorbed on assignment and setting it back to identity re-bakes
the geometry to local coords. There is no way to hold geometry-at-global with
Placement=identity via normal assignment.

Architectural; this test documents the desired (currently impossible) behaviour.
"""
from __future__ import annotations

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")

pytestmark = [
    pytest.mark.core,
    pytest.mark.xfail(
        strict=True,
        reason="FreeCAD: Part::Feature absorbs shape placement; geometry-at-global "
        "with identity placement is impossible via normal assignment",
    ),
]


def test_can_hold_global_geometry_with_identity_placement(freecad_session):
    doc = freecad_session.doc
    src = doc.addObject("Part::Box", "Src")
    src.Length = src.Width = src.Height = 10
    src.Placement.Base = FreeCAD.Vector(5, 0, 0)  # global x extent [5, 15]
    doc.recompute()

    solid = src.Shape.copy()
    solid.transformFreeCAD(src.getGlobalPlacement().toMatrix())  # bake to global

    clean = doc.addObject("Part::Feature", "Clean")
    clean.Shape = solid
    # Desired: geometry stays at global [5,15] AND placement is identity.
    assert clean.Placement.isIdentity(), (
        f"placement absorbed to {clean.Placement.Base} / {clean.Placement.Rotation}; "
        "cannot hold geometry-at-global with identity placement"
    )
    bbox = clean.Shape.BoundBox
    assert abs(bbox.XMin - 5.0) <= 1e-3 and abs(bbox.XMax - 15.0) <= 1e-3, (
        f"geometry not at global coords: X extent {bbox.XMin}..{bbox.XMax} != 5..15"
    )
