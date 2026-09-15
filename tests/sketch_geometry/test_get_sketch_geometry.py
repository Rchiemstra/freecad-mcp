"""Unit coverage for the typed ``get_sketch_geometry`` query slice."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import assembly_io_actions
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.get_sketch_geometry import run_get_sketch_geometry
from tests.typed_rpc_fakes import FakeDocument, FakeObject, collaborators

pytestmark = pytest.mark.unit


def test_get_sketch_geometry_observed_without_native_mutation():
    events: list[str] = []
    document = FakeDocument(events)
    document.objects["Sketch"] = FakeObject("Sketch")
    collab, _api = collaborators(document, events)
    payload = {
        "sketch_name": "Sketch",
        "geometry_count": 0,
        "geometry": [],
    }
    with patch.object(assembly_io_actions, "get_sketch_geometry", return_value=payload):
        result = run_get_sketch_geometry(collab, "Doc", "Sketch")

    assert result["success"] is True
    assert result["outcome"] == "observed"
    assert "commit" not in events


def test_missing_document_is_rejected():
    events: list[str] = []
    collab, _api = collaborators(None, events)

    result = run_get_sketch_geometry(collab, "Doc", "Sketch")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def test_missing_object_is_rejected():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)

    result = run_get_sketch_geometry(collab, "Doc", "Sketch")

    assert result["success"] is False
    assert result["error_code"] == "SKETCH_NOT_FOUND"
