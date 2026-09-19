"""D-26: pocket_feature must refuse a Body that has no solid to cut into.

FreeCAD's subtractive features fall back to *adding* their tool shape when the Body has no
base solid. Natively ``pocket_feature`` in a Body holding only a sketch committed a solid of
the tool's volume (e.g. 1000 mm3), the opposite of a pocket. The tool now refuses before
creating the Pocket, so the transaction rolls back with nothing added.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.pocket_feature import (
    apply_pocket_feature,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.pocket_feature_mutation import (
    PocketFeatureError,
)

pytestmark = pytest.mark.unit

COLLABORATORS = SimpleNamespace(
    part=Part,
    set_extrusion_symmetric=lambda feature, symmetric: None,
    set_feature_bool=lambda feature, names, value: None,
)


@pytest.fixture()
def doc():
    document = FreeCAD.newDocument(f"D26_{uuid.uuid4().hex[:8]}")
    yield document
    FreeCAD.closeDocument(document.Name)


def _square_sketch(body, name, size, z=0):
    sketch = body.newObject("Sketcher::SketchObject", name)
    xy = next(f for f in body.Origin.OriginFeatures if f.Role == "XY_Plane")
    sketch.AttachmentSupport = [(xy, "")]
    sketch.MapMode = "FlatFace"
    sketch.AttachmentOffset = FreeCAD.Placement(FreeCAD.Vector(0, 0, z), FreeCAD.Rotation())
    corners = [FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(size, 0, 0), FreeCAD.Vector(size, size, 0), FreeCAD.Vector(0, size, 0)]
    for start, end in zip(corners, corners[1:] + corners[:1]):
        sketch.addGeometry(Part.LineSegment(start, end))
    return sketch


def _pocket(doc, body, sketch_name):
    return apply_pocket_feature(doc, sketch_name, "Pocket", 5.0, body.Name, False, False, COLLABORATORS)


def test_pocket_in_a_body_without_a_solid_is_refused(doc):
    body = doc.addObject("PartDesign::Body", "Body")
    _square_sketch(body, "Cut", 10)
    doc.recompute()

    with pytest.raises(PocketFeatureError) as caught:
        _pocket(doc, body, "Cut")

    assert caught.value.code == "POCKET_NO_BASE_SOLID"
    assert "Body" in str(caught.value)
    assert doc.getObject("Pocket") is None
    assert body.Tip is None


def test_pocket_into_a_padded_body_is_still_applied(doc):
    body = doc.addObject("PartDesign::Body", "Body")
    base = _square_sketch(body, "Base", 20)
    pad = body.newObject("PartDesign::Pad", "Pad")
    pad.Profile = base
    pad.Length = 10
    body.Tip = pad
    _square_sketch(body, "Cut", 10, z=10)
    doc.recompute()

    receipt = _pocket(doc, body, "Cut")
    doc.recompute()

    assert receipt.name == "Pocket"
    assert body.Tip is doc.getObject("Pocket")
    assert body.Shape.Volume == pytest.approx(20 * 20 * 10 - 10 * 10 * 5)
