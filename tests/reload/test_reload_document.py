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
