"""D-17: the typed ``sketch_create`` RPC must accept and apply ``attachment_offset``.

The MCP client forwards ``attachment_offset`` to the ``sketch_create`` RPC, but the typed
handler that replaced ``sketch_public`` dropped the parameter, so the listener rejected every
call that used it with JSON-RPC ``-32602 Invalid params``.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import sketch_create as subject
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_create_mutation import SketchCreateError

pytestmark = pytest.mark.unit

OFFSET = {"Base": {"x": 0, "y": 0, "z": 430}}


class _Sketch:
    TypeId = "Sketcher::SketchObject"

    def __init__(self, name: str) -> None:
        self.Name = name
        self.Label = name
        self.AttachmentSupport: list[object] = []
        self.MapMode = "Deactivated"
        self.AttachmentOffset = "identity"


def _document():
    plane = SimpleNamespace(Name="XY_Plane", Label="XY_Plane")
    origin = SimpleNamespace(TypeId="App::Origin", OriginFeatures=[plane], Name="Origin")
    objects: dict[str, object] = {}

    def new_object(_type_id: str, name: str) -> _Sketch:
        sketch = _Sketch(name)
        objects[name] = sketch
        return sketch

    body = SimpleNamespace(TypeId="PartDesign::Body", Name="Seat", Origin=origin, newObject=new_object)
    objects["Seat"] = body
    doc = SimpleNamespace(Objects=[body, origin], getObject=objects.get)
    return doc, plane


def _codec(value):
    return ("placement", value)


def test_rpc_signature_accepts_attachment_offset():
    params = {
        "doc_name": "Chair",
        "sketch_name": "SeatSketch",
        "body_name": "Seat",
        "attach_to": "XY_Plane",
        "attachment_offset": OFFSET,
    }
    inspect.signature(subject.rpc_sketch_create).bind(None, **params)


def test_offset_is_applied_with_the_attachment():
    doc, plane = _document()
    receipt = subject.apply_sketch_create(doc, "SeatSketch", "Seat", "XY_Plane", OFFSET, object(), _codec)
    assert receipt.sketch.AttachmentSupport == [(plane, "")]
    assert receipt.sketch.MapMode == "FlatFace"
    assert receipt.sketch.AttachmentOffset == ("placement", OFFSET)


def test_offset_without_attach_to_is_rejected_before_any_object_exists():
    request = subject.build_sketch_create_request("Chair", "SeatSketch", "Seat", None, OFFSET)
    assert isinstance(request, dict)
    assert request["success"] is False
    assert request["error_code"] == "INVALID_ARGUMENT"


def test_non_object_offset_is_rejected():
    request = subject.build_sketch_create_request("Chair", "SeatSketch", "Seat", "XY_Plane", [0, 0, 430])
    assert isinstance(request, dict)
    assert request["error_code"] == "INVALID_ARGUMENT"


def test_missing_placement_codec_is_a_typed_error():
    doc, _plane = _document()
    with pytest.raises(SketchCreateError) as caught:
        subject.apply_sketch_create(doc, "SeatSketch", "Seat", "XY_Plane", OFFSET, object(), None)
    assert caught.value.code == "PLACEMENT_CODEC_UNAVAILABLE"
