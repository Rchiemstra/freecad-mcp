"""Worker protocol limits and unsupported GUI API checks."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import FreeCADGui

if not hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand = lambda *_args, **_kwargs: None

from addon.FreeCADMCP.rpc_server.worker_protocol import (
    CappedTextWriter,
    ProtocolError,
    reject_detectable_gui_usage,
    validate_subelement_reference,
)
from addon.FreeCADMCP.rpc_server import snapshot_service


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


@pytest.mark.parametrize("name", ["H_Axis", "V_Axis", "RootPoint"])
def test_validate_subelement_accepts_sketcher_semantic_names(name):
    edge = SimpleNamespace(isNull=lambda: False)
    target = SimpleNamespace(
        Name="BoltProfileSketch",
        Shape=_RaisingShape(),
        getSubObject=lambda requested: edge if requested == name else None,
    )
    validate_subelement_reference(target, name)


def test_validate_subelement_rejects_unknown_semantic_name():
    target = SimpleNamespace(
        Name="BoltProfileSketch",
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
