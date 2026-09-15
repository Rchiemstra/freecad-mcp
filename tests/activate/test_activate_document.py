"""Unit coverage for the typed ``activate_document`` lifecycle slice."""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.activate_document import run_activate_document
from tests.typed_rpc_fakes import FakeDocument, collaborators

pytestmark = pytest.mark.unit


def test_activate_document_verifies_without_native_mutation():
    events: list[str] = []
    document = FakeDocument(events, name="Target")
    collab, api = collaborators(document, events)

    result = run_activate_document(collab, "Target")

    assert result["success"] is True
    assert result["outcome"] == "verified"
    assert "commit" not in events
    assert api.document is document


def test_missing_document_is_rejected():
    events: list[str] = []
    collab, _api = collaborators(None, events)

    result = run_activate_document(collab, "Target")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
