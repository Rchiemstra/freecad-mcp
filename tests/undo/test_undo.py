"""Unit coverage for the typed ``undo`` history slice."""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.undo import run_undo
from tests.typed_rpc_fakes import FakeDocument, collaborators

pytestmark = pytest.mark.unit


def test_undo_verifies_without_native_mutation():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)

    result = run_undo(collab, "Doc")

    assert result["success"] is True
    assert result["outcome"] == "verified"
    assert "apply" in events
    assert "commit" not in events


def test_empty_undo_stack_is_rejected():
    events: list[str] = []
    document = FakeDocument(events)
    document.UndoCount = 0
    collab, _api = collaborators(document, events)

    result = run_undo(collab, "Doc")

    assert result["success"] is False
    assert result["error_code"] == "EMPTY_HISTORY_STACK"
    assert result["retry_safe"] is True


def test_missing_document_is_rejected():
    events: list[str] = []
    collab, _api = collaborators(None, events)

    result = run_undo(collab, "Doc")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
