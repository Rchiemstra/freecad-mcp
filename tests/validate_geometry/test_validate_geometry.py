"""Unit coverage for the typed ``validate_geometry`` query slice."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import measure_io_actions
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.validate_geometry import run_validate_geometry
from tests.typed_rpc_fakes import FakeDocument, FakeObject, collaborators

pytestmark = pytest.mark.unit


def test_validate_geometry_observed_without_native_mutation():
    events: list[str] = []
    document = FakeDocument(events)
    document.objects["Box"] = FakeObject("Box")
    collab, _api = collaborators(document, events)
    payload = {
        "object": "Box",
        "is_null": False,
        "is_valid": True,
        "is_closed": True,
        "volume_mm3": 1000.0,
        "area_mm2": 600.0,
        "face_count": 6,
        "edge_count": 12,
        "vertex_count": 8,
        "shape_type": "Solid",
        "check_ok": True,
        "check_errors": [],
    }
    with patch.object(measure_io_actions, "validate_geometry", return_value=payload):
        result = run_validate_geometry(collab, "Doc", "Box")

    assert result["success"] is True
    assert result["outcome"] == "observed"
    assert "commit" not in events


def test_missing_document_is_rejected():
    events: list[str] = []
    collab, _api = collaborators(None, events)

    result = run_validate_geometry(collab, "Doc", "Box")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def test_missing_object_is_rejected():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)

    result = run_validate_geometry(collab, "Doc", "Box")

    assert result["success"] is False
    assert result["error_code"] == "OBJECT_NOT_FOUND"
