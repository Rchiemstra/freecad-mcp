"""D-30: world-frame shape resolution must not apply an object's own Placement twice.

In FreeCAD, ``obj.Shape`` of a placed feature already carries ``obj.Placement``; only the
enclosing GeoFeatureGroups (App::Part, Body) remain to be applied. ``resolve_global_shape``
applied the full global placement on top, so every placed non-Link object was measured twice
transformed: natively a 10 mm Part::Box at x=5 rotated 90 deg about X reported x 10..20 and
z -10..0 (correct: x 5..15, z 0..10), and a symmetric revolve on the XZ plane looked
asymmetric. The fake-shape suite in ``test_world_shape.py`` modeled ``obj.Shape`` as unplaced
and could not see this; these tests use real FreeCAD shapes.
"""

from __future__ import annotations

import uuid

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
pytest.importorskip("Part")

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import (
    world_shape_actions,
)

pytestmark = pytest.mark.unit


@pytest.fixture()
def doc():
    document = FreeCAD.newDocument(f"D30_{uuid.uuid4().hex[:8]}")
    yield document
    FreeCAD.closeDocument(document.Name)


def _box(doc, name, placement):
    box = doc.addObject("Part::Box", name)
    box.Length = box.Width = box.Height = 10
    box.Placement = placement
    return box


def _bounds(bound_box):
    return tuple(
        round(value, 6)
        for value in (
            bound_box.XMin, bound_box.YMin, bound_box.ZMin,
            bound_box.XMax, bound_box.YMax, bound_box.ZMax,
        )
    )


def _resolved_bounds(obj):
    shape, _meta = world_shape_actions.resolve_global_shape(obj)
    return _bounds(shape.BoundBox)


ROTATED_X90_AT_5 = FreeCAD.Placement(FreeCAD.Vector(5, 0, 0), FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90))


def test_placed_part_feature_is_transformed_once(doc):
    box = _box(doc, "Box", ROTATED_X90_AT_5)
    doc.recompute()
    assert _resolved_bounds(box) == (5, -10, 0, 15, 0, 10)
    assert _resolved_bounds(box) == _bounds(box.Shape.BoundBox)


def test_feature_in_translated_part_applies_the_container_once(doc):
    part = doc.addObject("App::Part", "Part")
    part.Placement = FreeCAD.Placement(FreeCAD.Vector(100, 0, 0), FreeCAD.Rotation())
    box = _box(doc, "Box", ROTATED_X90_AT_5)
    part.addObject(box)
    doc.recompute()
    assert _resolved_bounds(box) == (105, -10, 0, 115, 0, 10)


def test_symmetric_revolve_on_xz_plane_stays_symmetric(doc):
    import Sketcher

    Part = pytest.importorskip("Part")
    body = doc.addObject("PartDesign::Body", "Body")
    sketch = body.newObject("Sketcher::SketchObject", "Sketch")
    xz = next(f for f in body.Origin.OriginFeatures if f.Role == "XZ_Plane")
    sketch.AttachmentSupport = [(xz, "")]
    sketch.MapMode = "FlatFace"
    points = [FreeCAD.Vector(10, 0, 0), FreeCAD.Vector(20, 0, 0), FreeCAD.Vector(20, 10, 0), FreeCAD.Vector(10, 10, 0)]
    for start, end in zip(points, points[1:] + points[:1]):
        sketch.addGeometry(Part.LineSegment(start, end))
    for index in range(4):
        sketch.addConstraint(Sketcher.Constraint("Coincident", index, 2, (index + 1) % 4, 1))
    revolve = body.newObject("PartDesign::Revolution", "Revolve")
    revolve.Profile = sketch
    revolve.ReferenceAxis = (sketch, ["V_Axis"])
    revolve.Angle = 90
    if "SideType" in revolve.PropertiesList:
        revolve.SideType = "Symmetric"
    else:
        revolve.Midplane = True
    doc.recompute()
    assert revolve.Shape.isValid()
    _x_min, y_min, z_min, _x_max, y_max, z_max = _resolved_bounds(revolve)
    assert y_min == pytest.approx(-y_max, abs=1e-6)
    assert (z_min, z_max) == pytest.approx((0, 10), abs=1e-6)
    assert _resolved_bounds(revolve) == _bounds(revolve.Shape.BoundBox)
