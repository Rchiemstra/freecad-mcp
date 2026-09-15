"""Unit coverage for the typed ``inspect_geometry`` query slice."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import diagnostics_io_actions
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.inspect_geometry import run_inspect_geometry
from tests.typed_rpc_fakes import FakeDocument, FakeObject, collaborators

pytestmark = pytest.mark.unit


def test_inspect_geometry_observed_without_native_mutation():
    events: list[str] = []
    document = FakeDocument(events)
    document.objects["Box"] = FakeObject("Box")
    collab, _api = collaborators(document, events)
    payload = {
        "object": "Box",
        "type_id": "Part::Feature",
        "placement": {"base": {"x": 0.0, "y": 0.0, "z": 0.0}, "rotation": ""},
        "global_placement": {"base": {"x": 0.0, "y": 0.0, "z": 0.0}, "rotation": ""},
        "parent_chain": [],
        "local_bbox": {"xmin": 0.0},
        "global_bbox": {"xmin": 0.0},
    }
    with patch.object(diagnostics_io_actions, "inspect_geometry", return_value=payload):
        result = run_inspect_geometry(collab, "Doc", "Box", None)

    assert result["success"] is True
    assert result["outcome"] == "observed"
    assert "commit" not in events


def test_missing_document_is_rejected():
    events: list[str] = []
    collab, _api = collaborators(None, events)

    result = run_inspect_geometry(collab, "Doc", "Box", None)

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def test_missing_object_is_rejected():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)

    result = run_inspect_geometry(collab, "Doc", "Box", None)

    assert result["success"] is False
    assert result["error_code"] == "OBJECT_NOT_FOUND"
