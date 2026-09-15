"""Unit coverage for the typed ``spreadsheet_list_aliases`` query slice."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import spreadsheet_list_aliases as subject
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.spreadsheet_list_aliases import run_spreadsheet_list_aliases
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import spreadsheet_alias_ops
from tests.typed_rpc_fakes import FakeDocument, collaborators

pytestmark = pytest.mark.unit


def _sheet(name: str = "Sheet1") -> SimpleNamespace:
    return SimpleNamespace(
        Name=name,
        Label=name,
        TypeId="Spreadsheet::Sheet",
        getAlias=lambda addr: "width" if addr == "A1" else None,
        getNonEmptyCells=lambda: ["A1"],
    )


def test_spreadsheet_list_aliases_observed_without_native_mutation():
    events: list[str] = []
    document = FakeDocument(events)
    document.objects["Sheet1"] = _sheet()
    collab, _api = collaborators(document, events)
    aliases = {"width": "A1"}
    with patch.object(spreadsheet_alias_ops, "collect_spreadsheet_aliases", return_value=aliases):
        result = run_spreadsheet_list_aliases(collab, "Doc", "Sheet1")

    assert result["success"] is True
    assert result["outcome"] == "observed"
    assert result["sheet"] == "Sheet1"
    assert result["aliases"] == aliases
    assert "commit" not in events


def test_missing_document_is_rejected():
    events: list[str] = []
    collab, _api = collaborators(None, events)
    result = run_spreadsheet_list_aliases(collab, "Doc", "Sheet1")
    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def test_missing_sheet_is_rejected():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)
    result = run_spreadsheet_list_aliases(collab, "Doc", "Sheet1")
    assert result["success"] is False
    assert result["error_code"] == "OBJECT_NOT_FOUND"


def test_spreadsheet_list_aliases_has_typed_rpc_handler():
    assert subject.TYPED_RPC_HANDLER[0] == "spreadsheet_list_aliases"
    assert callable(subject.TYPED_RPC_HANDLER[1])
