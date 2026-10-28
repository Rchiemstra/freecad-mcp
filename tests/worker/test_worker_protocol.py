"""Worker protocol limits and unsupported GUI API checks."""

from __future__ import annotations

from types import SimpleNamespace

import FreeCADGui
import pytest

if not hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand = lambda *_args, **_kwargs: None

from addon.FreeCADMCP.rpc_server import snapshot_service
from addon.FreeCADMCP.rpc_server.worker_protocol import (
    CappedTextWriter,
    ProtocolError,
    reject_detectable_gui_usage,
    validate_subelement_reference,
)


class _RaisingShape:
    def getElement(self, name):
        raise ValueError(f"Invalid shape name {name}")


class _EmptyShape:
    Faces = ()
    Edges = ()
    Vertexes = ()

    def getElement(self, name):
        raise ValueError(f"Invalid shape name {name}")


class _NamedElementShape:
    def __init__(self, elements):
        self._elements = elements

    def getElement(self, name):
        if name not in self._elements:
            raise ValueError(f"Invalid shape name {name}")
        return self._elements[name]


def test_stdout_is_capped_while_writing():
    writer = CappedTextWriter(limit=5)
    assert writer.write("abc") == 3
    assert writer.write("defgh") == 5
    assert writer.getvalue() == "abcde"
    assert writer.truncated is True


@pytest.mark.parametrize(
    "code",
    [
        "import FreeCADGui",
        "from FreeCADGui import Selection",
        "Gui.activeDocument()",
        "FreeCAD.Gui.ActiveDocument",
    ],
)
def test_detectable_worker_gui_usage_is_rejected(code):
    with pytest.raises(ProtocolError, match="unsupported"):
        reject_detectable_gui_usage(code)


def test_dynamic_import_is_not_misrepresented_as_a_security_boundary():
    # Static inspection is best effort; the worker also supplies an API-level
    # import guard, but neither mechanism is a security sandbox.
    reject_detectable_gui_usage("__import__('Free' + 'CADGui')")


def test_selection_state_includes_selected_subelements(monkeypatch):
    selection = SimpleNamespace(
        getSelectionEx=lambda: [
            SimpleNamespace(
                DocumentName="Model",
                ObjectName="Box",
                SubElementNames=["Face1", "Edge2"],
            )
        ]
    )
    monkeypatch.setattr(snapshot_service.FreeCADGui, "Selection", selection, raising=False)
    assert snapshot_service._selection_state() == [
        ("Model", "Box", ("Face1", "Edge2"))
    ]


@pytest.mark.parametrize("name", ["H_Axis", "V_Axis", "N_Axis", "RootPoint"])
def test_validate_subelement_accepts_sketcher_pseudo_subelements(name):
    target = SimpleNamespace(
        Name="BoltProfileSketch",
        TypeId="Sketcher::SketchObject",
        Shape=_RaisingShape(),
        getSubObject=lambda _requested: None,
    )
    validate_subelement_reference(target, name)


def test_validate_subelement_rejects_unknown_semantic_name():
    target = SimpleNamespace(
        Name="BoltProfileSketch",
        TypeId="Sketcher::SketchObject",
        Shape=_EmptyShape(),
        getSubObject=lambda _name: None,
    )
    with pytest.raises(ProtocolError, match="DoesNotExist"):
        validate_subelement_reference(target, "DoesNotExist")


@pytest.mark.parametrize("name", ["../x", "a/b", "a\\b", "bad\nname", "", ".."])
def test_validate_subelement_rejects_unsafe_names(name):
    def _boom(_requested):
        raise AssertionError("resolvers must not run for unsafe names")

    target = SimpleNamespace(
        Name="Sketch",
        Shape=SimpleNamespace(getElement=_boom),
        getSubObject=_boom,
    )
    with pytest.raises(ProtocolError, match="does not exist"):
        validate_subelement_reference(target, name)


@pytest.mark.parametrize("name", ["Face999", "Edge999", "Vertex999"])
def test_validate_subelement_rejects_out_of_range_indexed_names(name):
    target = SimpleNamespace(Name="Box", Shape=_EmptyShape())
    with pytest.raises(ProtocolError, match="does not exist"):
        validate_subelement_reference(target, name)


def test_validate_subelement_falls_back_to_shape_get_element():
    edge = SimpleNamespace(isNull=lambda: False)
    target = SimpleNamespace(
        Name="Box",
        Shape=_NamedElementShape({"CustomEdge": edge}),
        getSubObject=lambda _name: None,
    )
    validate_subelement_reference(target, "CustomEdge")


def test_validate_subelement_accepts_origin_datum_without_a_shape():
    datum = SimpleNamespace(Name="XY_Plane001", TypeId="App::Plane")
    null_shape = SimpleNamespace(isNull=lambda: True)
    calls = []

    def get_subobject(name, ret_type=0):
        calls.append((name, ret_type))
        if name == "Origin002.XY_Plane001.":
            return datum if ret_type == 1 else null_shape
        return None

    target = SimpleNamespace(Name="Arm", Shape=_EmptyShape(), getSubObject=get_subobject)
    validate_subelement_reference(target, "Origin002.XY_Plane001.")
    assert calls[-1] == ("Origin002.XY_Plane001.", 1)
    with pytest.raises(ProtocolError):
        validate_subelement_reference(target, "Origin002.MissingPlane.")


def test_validate_subelement_does_not_use_owner_fallback_for_missing_geometry():
    owner = SimpleNamespace(Name="Body")

    def get_subobject(name, ret_type=0):
        return owner if ret_type == 1 else None

    target = SimpleNamespace(Name="Body", Shape=_EmptyShape(), getSubObject=get_subobject)
    with pytest.raises(ProtocolError):
        validate_subelement_reference(target, "MissingSemantic")
    with pytest.raises(ProtocolError):
        validate_subelement_reference(target, "Face999")
