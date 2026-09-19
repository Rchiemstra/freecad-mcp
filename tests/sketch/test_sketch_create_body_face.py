"""D-04: ``sketch_create(attach_to="<Body>:FaceN")`` must attach to the Body's Tip face.

``find_faces`` is normally run on the Body and returns ``FaceN`` of ``Body.Shape`` (= the Tip's
shape). Supporting a sketch on the Body object itself makes the sketch depend on the Body that
contains it: a dependency cycle, and the GUI mutation hung for 30 s and committed nothing.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import sketch_create as subject
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_create_mutation import SketchCreateError

pytestmark = pytest.mark.unit


class _Sketch:
    TypeId = "Sketcher::SketchObject"

    def __init__(self, name: str) -> None:
        self.Name = name
        self.Label = name
        self.AttachmentSupport: list[object] = []
        self.MapMode = "Deactivated"


def _document(*, tip: object | None):
    objects: dict[str, object] = {}

    def new_object(_type_id: str, name: str) -> _Sketch:
        sketch = _Sketch(name)
        objects[name] = sketch
        return sketch

    body = SimpleNamespace(
        TypeId="PartDesign::Body",
        Name="Seat",
        Origin=None,
        Tip=tip,
        newObject=new_object,
        isDerivedFrom=lambda type_id: type_id == "PartDesign::Body",
    )
    objects["Seat"] = body
    if tip is not None:
        objects[tip.Name] = tip
    doc = SimpleNamespace(Objects=list(objects.values()), getObject=objects.get)
    return doc


def test_body_face_resolves_to_tip_face():
    pad = SimpleNamespace(Name="SeatPad", TypeId="PartDesign::Pad")
    doc = _document(tip=pad)
    receipt = subject.apply_sketch_create(doc, "ScrewSketch", "Seat", "Seat:Face6", None, object(), None)
    assert receipt.sketch.AttachmentSupport == [(pad, "Face6")]
    assert receipt.sketch.MapMode == "FlatFace"


def test_feature_face_is_unchanged():
    pad = SimpleNamespace(Name="SeatPad", TypeId="PartDesign::Pad")
    doc = _document(tip=pad)
    receipt = subject.apply_sketch_create(doc, "ScrewSketch", "Seat", "SeatPad:Face6", None, object(), None)
    assert receipt.sketch.AttachmentSupport == [(pad, "Face6")]


def test_body_without_tip_is_refused_instead_of_creating_a_cycle():
    doc = _document(tip=None)
    with pytest.raises(SketchCreateError) as caught:
        subject.apply_sketch_create(doc, "ScrewSketch", "Seat", "Seat:Face6", None, object(), None)
    assert caught.value.code == "SUPPORT_NOT_FOUND"
