"""Unit coverage for the typed ``bounding_box`` query slice."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import measure_io_actions
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.bounding_box import run_bounding_box
from tests.typed_rpc_fakes import FakeDocument, FakeObject, collaborators

pytestmark = pytest.mark.unit


def test_bounding_box_observed_without_native_mutation():
    events: list[str] = []
    document = FakeDocument(events)
    document.objects["Box"] = FakeObject("Box")
    collab, _api = collaborators(document, events)
    payload = {
        "object": "Box",
        "xmin": 0.0,
        "ymin": 0.0,
        "zmin": 0.0,
        "xmax": 1.0,
        "ymax": 1.0,
        "zmax": 1.0,
        "dx": 1.0,
        "dy": 1.0,
        "dz": 1.0,
        "diagonal": 1.732,
        "frame": "global",
    }
    with patch.object(measure_io_actions, "bounding_box", return_value=payload):
        result = run_bounding_box(collab, "Doc", "Box")

    assert result["success"] is True
    assert result["outcome"] == "observed"
    assert "commit" not in events


def test_missing_document_is_rejected():
    events: list[str] = []
    collab, _api = collaborators(None, events)

    result = run_bounding_box(collab, "Doc", "Box")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def test_missing_object_is_rejected():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)

    result = run_bounding_box(collab, "Doc", "Box")

    assert result["success"] is False
    assert result["error_code"] == "OBJECT_NOT_FOUND"
