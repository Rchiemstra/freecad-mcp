"""Unit coverage for the typed ``create_document`` lifecycle slice."""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.create_document import run_create_document
from tests.typed_rpc_fakes import collaborators


pytestmark = pytest.mark.unit


def test_create_document_verifies_without_native_mutation():
    events: list[str] = []
    collab, api = collaborators(None, events)

    result = run_create_document(collab, "CreatedDoc")

    assert result["success"] is True
    assert result["outcome"] == "verified"
    assert result["document_name"] == "CreatedDoc"
    assert "commit" not in events
    assert api.getDocument("CreatedDoc") is not None


def test_duplicate_name_is_rejected():
    events: list[str] = []
    collab, api = collaborators(None, events)
    api.newDocument("CreatedDoc")

    result = run_create_document(collab, "CreatedDoc")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_ALREADY_EXISTS"


def test_invalid_arguments_are_rejected():
    events: list[str] = []
    collab, _api = collaborators(None, events)

    result = run_create_document(collab, "")

    assert result["success"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"


def test_missing_freecad_is_rejected():
    from types import SimpleNamespace

    result = run_create_document(SimpleNamespace(freecad=None), "CreatedDoc")
    assert result["success"] is False
    assert result["error_code"] == "FREECAD_UNAVAILABLE"


def test_perform_failure_without_document_returns_rejection():
    from types import SimpleNamespace

    def broken_new(_name: str):
        raise RuntimeError("newDocument failed")

    collab = SimpleNamespace(
        freecad=SimpleNamespace(
            getDocument=lambda _name: None,
            newDocument=broken_new,
            closeDocument=lambda _name: None,
        )
    )
    result = run_create_document(collab, "CreatedDoc")
    assert result["success"] is False
    assert result["outcome"] == "rejected"
    assert result["error_code"] == "CREATE_DOCUMENT_FAILED"
