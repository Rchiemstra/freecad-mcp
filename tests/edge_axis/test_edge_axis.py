"""Unit coverage for the typed ``edge_axis`` query slice."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import diagnostics_shape_actions
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.edge_axis import run_edge_axis
from tests.typed_rpc_fakes import FakeDocument, FakeObject, collaborators

pytestmark = pytest.mark.unit


def test_edge_axis_observed_without_native_mutation():
    events: list[str] = []
    document = FakeDocument(events)
    document.objects["Box"] = FakeObject("Box")
    collab, _api = collaborators(document, events)
    payload = {
        "object": "Box",
        "subshape": "Edge1",
        "type": "Line",
        "global_center": {"x": 0.0, "y": 0.0, "z": 0.0},
        "global_normal": {"x": 1.0, "y": 0.0, "z": 0.0},
    }
    with patch.object(diagnostics_shape_actions, "edge_axis", return_value=payload):
        result = run_edge_axis(collab, "Doc", "Box", "Edge1")

    assert result["success"] is True
    assert result["outcome"] == "observed"
    assert "commit" not in events


def test_missing_document_is_rejected():
    events: list[str] = []
    collab, _api = collaborators(None, events)

    result = run_edge_axis(collab, "Doc", "Box", "Edge1")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def test_missing_object_is_rejected():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)

    result = run_edge_axis(collab, "Doc", "Box", "Edge1")

    assert result["success"] is False
    assert result["error_code"] == "OBJECT_NOT_FOUND"
