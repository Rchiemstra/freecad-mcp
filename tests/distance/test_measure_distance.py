"""Unit coverage for the typed ``measure_distance`` query slice."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import measure_io_actions
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.measure_distance import run_measure_distance
from tests.typed_rpc_fakes import FakeDocument, FakeObject, collaborators

pytestmark = pytest.mark.unit


def test_measure_distance_observed_without_native_mutation():
    events: list[str] = []
    document = FakeDocument(events)
    document.objects["Box"] = FakeObject("Box")
    collab, _api = collaborators(document, events)
    payload = {
        "distance": 0.0,
        "unit": "mm",
    }
    with patch.object(measure_io_actions, "measure_distance", return_value=payload):
        result = run_measure_distance(collab, "Doc", "Box", "Box")

    assert result["success"] is True
    assert result["outcome"] == "observed"
    assert "commit" not in events


def test_missing_document_is_rejected():
    events: list[str] = []
    collab, _api = collaborators(None, events)

    result = run_measure_distance(collab, "Doc", "Box", "Box")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def test_missing_object_is_rejected():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)

    result = run_measure_distance(collab, "Doc", "Box", "Box")

    assert result["success"] is False
    assert result["error_code"] == "OBJECT_NOT_FOUND"
