"""Unit coverage for the typed ``capture_state`` query slice."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import diagnostics_io_actions
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.capture_state import run_capture_state
from tests.typed_rpc_fakes import FakeDocument, FakeObject, collaborators

pytestmark = pytest.mark.unit


def test_capture_state_observed_without_native_mutation():
    events: list[str] = []
    document = FakeDocument(events)
    document.objects["Seed"] = FakeObject("Seed")
    collab, _api = collaborators(document, events)
    payload = {"doc": "Doc", "objects": {"Seed": {"name": "Seed"}}}
    with patch.object(diagnostics_io_actions, "capture_state", return_value=payload):
        result = run_capture_state(collab, "Doc", ["Seed"])

    assert result["success"] is True
    assert result["outcome"] == "observed"
    assert "Seed" in result["objects"]
    assert "commit" not in events


def test_missing_document_is_rejected():
    events: list[str] = []
    collab, _api = collaborators(None, events)

    result = run_capture_state(collab, "Doc", ["Seed"])

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def test_io_failure_is_rejected():
    events: list[str] = []
    document = FakeDocument(events)
    document.objects["Seed"] = FakeObject("Seed")
    collab, _api = collaborators(document, events)
    with patch.object(diagnostics_io_actions, "capture_state", side_effect=RuntimeError("capture failed")):
        result = run_capture_state(collab, "Doc", ["Seed"])

    assert result["success"] is False
    assert result["error_code"] == "CAPTURE_STATE_FAILED"
