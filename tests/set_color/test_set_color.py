"""Unit coverage for the typed ``set_color`` query slice."""

from __future__ import annotations

from types import SimpleNamespace

from unittest.mock import patch

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.set_color import run_set_color
from tests.typed_rpc_fakes import FakeDocument, FakeObject, collaborators

pytestmark = pytest.mark.unit


def test_set_color_applied_without_native_mutation():
    events: list[str] = []
    document = FakeDocument(events)
    box = FakeObject("Box")
    box.ViewObject = SimpleNamespace(ShapeColor=None, Transparency=0)
    document.objects["Box"] = box
    collab, _api = collaborators(document, events)
    result = run_set_color(collab, "Doc", "Box", 1.0, 0.0, 0.0, 0.0)

    assert result["success"] is True
    assert result["outcome"] == "applied"
    assert "commit" not in events


def test_missing_document_is_rejected():
    events: list[str] = []
    collab, _api = collaborators(None, events)

    result = run_set_color(collab, "Doc", "Box", 1.0, 0.0, 0.0, 0.0)

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def test_missing_object_is_rejected():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)

    result = run_set_color(collab, "Doc", "Box", 1.0, 0.0, 0.0, 0.0)

    assert result["success"] is False
    assert result["error_code"] == "OBJECT_NOT_FOUND"
