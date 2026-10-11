"""Unit coverage for the typed ``get_global_shape`` query slice."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import measure_io_actions
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.get_global_shape import run_get_global_shape
from freecad_mcp._shared.protocol.get_global_shape_contract import parse_get_global_shape_response
from tests.typed_rpc_fakes import FakeDocument, FakeObject, collaborators

pytestmark = pytest.mark.unit


def test_get_global_shape_observed_without_native_mutation():
    events: list[str] = []
    document = FakeDocument(events)
    document.objects["Box"] = FakeObject("Box")
    collab, _api = collaborators(document, events)
    payload = {
        "object": "Box",
        "frame": "global",
        "volume_mm3": 1000.0,
        "area_mm2": 600.0,
        "center_of_mass": {"x": 0.0, "y": 0.0, "z": 0.0},
        "bbox": {"xmin": 0.0, "ymin": 0.0, "zmin": 0.0, "xmax": 10.0, "ymax": 10.0, "zmax": 10.0},
        "solids": 1,
        "faces": 6,
        "edges": 12,
    }
    with patch.object(measure_io_actions, "get_global_shape", return_value=payload):
        result = run_get_global_shape(collab, "Doc", "Box")

    assert result["success"] is True
    assert result["outcome"] == "observed"
    assert "commit" not in events


def test_missing_document_is_rejected():
    events: list[str] = []
    collab, _api = collaborators(None, events)

    result = run_get_global_shape(collab, "Doc", "Box")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def test_missing_object_is_rejected():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)

    result = run_get_global_shape(collab, "Doc", "Box")

    assert result["success"] is False
    assert result["error_code"] == "OBJECT_NOT_FOUND"


def _geometry_response(shape, monkeypatch):
    """Keep geometry summarization and the client contract on the real path."""
    events = []
    document = FakeDocument(events)
    document.objects["Shape"] = FakeObject("Shape")
    collab, _api = collaborators(document, events)
    monkeypatch.setattr(measure_io_actions, "resolve_global_shape", lambda _obj: (shape, {}))
    monkeypatch.setattr(
        measure_io_actions,
        "_freecad",
        lambda: SimpleNamespace(Vector=lambda x, y, z: SimpleNamespace(x=x, y=y, z=z)),
    )
    return parse_get_global_shape_response(run_get_global_shape(collab, "Doc", "Shape"))


def _shape_summary(**properties):
    values = {
        "BoundBox": SimpleNamespace(
            XMin=0.0, YMin=0.0, ZMin=0.0,
            XMax=8.0, YMax=8.0, ZMax=8.0,
            XLength=8.0, YLength=8.0, ZLength=8.0, DiagonalLength=13.856406,
        ),
        "Volume": 0.0,
        "Area": 0.0,
    }
    values.update(properties)
    return SimpleNamespace(**values)


def test_shape_center_of_mass_survives_the_client_contract(monkeypatch):
    """A specialized shape with a direct COM remains a passing geometry path."""
    shape = _shape_summary(
        CenterOfMass=SimpleNamespace(x=3.0, y=4.0, z=5.0),
        Volume=1000.0, Area=600.0,
        Solids=[object()], Faces=[object()] * 6, Edges=[object()] * 12,
    )

    result = _geometry_response(shape, monkeypatch)

    assert result["success"] is True, result
    assert result["outcome"] == "observed"
    assert result["center_of_mass"] == pytest.approx([3.0, 4.0, 5.0])
    assert result["bbox"]["xmax"] == pytest.approx(8.0)
    assert result["volume_mm3"] == pytest.approx(1000.0)
    assert result["area_mm2"] == pytest.approx(600.0)
    assert (result["solids"], result["faces"], result["edges"]) == (1, 6, 12)


@pytest.mark.parametrize("kind,weight", [("Solids", "Volume"), ("Faces", "Area"), ("Edges", "Length")])
def test_generic_shape_uses_specialized_topology_centers(monkeypatch, kind, weight):
    """Part.Shape copies lack a direct COM, but their topology carries it."""
    topology = {"Solids": [], "Faces": [], "Edges": []}
    topology[kind] = [
        SimpleNamespace(**{weight: 1.0}, CenterOfMass=SimpleNamespace(x=0.0, y=2.0, z=4.0)),
        SimpleNamespace(**{weight: 3.0}, CenterOfMass=SimpleNamespace(x=8.0, y=6.0, z=8.0)),
    ]
    shape = _shape_summary(
        Volume=4.0 if kind == "Solids" else 0.0,
        Area=4.0 if kind == "Faces" else 0.0,
        **topology,
    )

    result = _geometry_response(shape, monkeypatch)

    assert result["success"] is True, result
    assert result["outcome"] == "observed"
    assert result["center_of_mass"] == pytest.approx([6.0, 5.0, 7.0])
    assert result[kind.lower()] == 2
