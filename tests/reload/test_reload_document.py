"""Unit coverage for the typed ``reload_document`` lifecycle slice."""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.reload_document import run_reload_document
from tests.typed_rpc_fakes import FakeDocument, collaborators

pytestmark = pytest.mark.unit


def test_reload_document_verifies_without_native_mutation():
    events: list[str] = []
    document = FakeDocument(events)
    collab, api = collaborators(document, events)

    result = run_reload_document(collab, "Doc")

    assert result["success"] is True
    assert result["outcome"] == "verified"
    assert "commit" not in events
    assert api.getDocument("Doc") is not None


def test_missing_document_is_rejected():
    events: list[str] = []
    collab, _api = collaborators(None, events)

    result = run_reload_document(collab, "Doc")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def test_a_document_with_unsaved_changes_is_not_reloaded():
    """reload_document reported success and silently threw the edits away."""

    events: list[str] = []
    document = FakeDocument(events)
    document.hasPendingFileChanges = lambda: True
    collab, api = collaborators(document, events)

    result = run_reload_document(collab, "Doc")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_HAS_UNSAVED_CHANGES"
    assert "save_document" in result["error"]
    assert api.getDocument("Doc") is document


def test_a_reload_reports_the_name_it_was_reopened_under():
    """Reopening names the document after its file; the caller must learn it."""

    events: list[str] = []
    document = FakeDocument(events)
    document.FileName = "/tmp/stress_sk.FCStd"
    document.hasPendingFileChanges = lambda: False
    collab, _api = collaborators(document, events)

    result = run_reload_document(collab, "Doc")

    assert result["success"] is True
    assert result["document_name"] == "stress_sk"
    assert result["previous_name"] == "Doc"
