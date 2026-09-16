"""Unit coverage for the typed ``get_global_shape`` query slice."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import measure_io_actions
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.get_global_shape import run_get_global_shape
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
