"""Regression coverage for atomic sketch creation and attachment."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_create_helpers import (
    apply_create_attach_to,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_gui_create import (
    sketch_create_gui,
)

pytestmark = pytest.mark.unit


class _Sketch:
    Name = "Sketch"
    AttachmentOffset = None

    def __init__(self):
        self.AttachmentSupport = []
        self.MapMode = "Deactivated"


def _body_document(*, include_plane: bool = True):
    plane = SimpleNamespace(Name="XZ_Plane", Label="XZ-plane")
    origin = SimpleNamespace(
        TypeId="App::Origin",
        OriginFeatures=[plane] if include_plane else [],
    )
    sketch = _Sketch()
    body = SimpleNamespace(
        TypeId="PartDesign::Body",
        Group=[sketch],
        Origin=origin,
    )
    document = SimpleNamespace(Objects=[body, origin])
    return document, sketch, plane


def test_create_attachment_resolves_freecad_plane_by_internal_name():
    document, sketch, plane = _body_document()

    error = apply_create_attach_to(sketch, document, "XZ_Plane")

    assert error is None
    assert sketch.AttachmentSupport == [(plane, "")]
    assert sketch.MapMode == "FlatFace"


def test_create_attachment_fails_closed_instead_of_emulating_with_placement():
    document, sketch, _plane = _body_document(include_plane=False)

    error = apply_create_attach_to(sketch, document, "XZ_Plane")

    assert error == "Origin plane not found: XZ_Plane"
    assert sketch.MapMode == "Deactivated"
    assert not hasattr(sketch, "Placement")


def test_create_attachment_rejects_unknown_support_syntax():
    document, sketch, _plane = _body_document()

    error = apply_create_attach_to(sketch, document, "not-a-plane")

    assert error == "Unsupported attach_to: not-a-plane"
    assert sketch.MapMode == "Deactivated"


def test_create_applies_attachment_offset_in_same_callback():
    document, sketch, _plane = _body_document()
    body = document.Objects[0]
    document.getObject = lambda name: body if name == "Body" else None
    document.recompute = lambda: None
    body.newObject = lambda type_id, name: sketch
    placement = object()
    freecad = SimpleNamespace(
        getDocument=lambda name: document if name == "Doc" else None,
        Console=SimpleNamespace(PrintMessage=lambda _message: None),
    )

    result = sketch_create_gui(
        "Doc",
        "Sketch",
        "Body",
        "XZ_Plane",
        {"Base": {"z": 10}},
        freecad=freecad,
        dict_to_placement=lambda _value: placement,
    )

    assert result is True
    assert sketch.MapMode == "FlatFace"
    assert sketch.AttachmentOffset is placement


def test_create_rejects_inert_offset_without_attachment():
    document, sketch, _plane = _body_document()
    document.getObject = lambda _name: None
    freecad = SimpleNamespace(getDocument=lambda _name: document)

    result = sketch_create_gui(
        "Doc",
        "Sketch",
        None,
        None,
        {"Base": {"z": 10}},
        freecad=freecad,
        dict_to_placement=lambda _value: object(),
    )

    assert result == "attachment_offset requires attach_to during sketch creation."
    assert sketch.MapMode == "Deactivated"
