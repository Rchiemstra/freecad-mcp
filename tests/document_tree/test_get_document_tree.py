"""Unit coverage for the typed ``get_document_tree`` query slice."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import assembly_io_actions
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.get_document_tree import run_get_document_tree
from tests.typed_rpc_fakes import FakeDocument, collaborators

pytestmark = pytest.mark.unit


def test_get_document_tree_observed_without_native_mutation():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)
    payload = {
        "doc_name": "Doc",
        "root_filter": "",
        "max_depth": 4,
        "roots": [],
    }
    with patch.object(assembly_io_actions, "get_document_tree", return_value=payload):
        result = run_get_document_tree(collab, "Doc")

    assert result["success"] is True
    assert result["outcome"] == "observed"
    assert "commit" not in events


def test_missing_document_is_rejected():
    events: list[str] = []
    collab, _api = collaborators(None, events)

    result = run_get_document_tree(collab, "Doc")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
