"""Unit coverage for the typed ``spreadsheet_get_cells`` query slice."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import spreadsheet_get_cells as subject
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.spreadsheet_get_cells import run_spreadsheet_get_cells
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import spreadsheet_cell_ops
from tests.typed_rpc_fakes import FakeDocument, collaborators

pytestmark = pytest.mark.unit


def _sheet(name: str = "Sheet1") -> SimpleNamespace:
    return SimpleNamespace(
        Name=name,
        Label=name,
        TypeId="Spreadsheet::Sheet",
        get=lambda addr: "42",
        getContents=lambda addr: "42",
        getAlias=lambda addr: None,
        getCellFromAlias=lambda alias: None,
        getNonEmptyCells=lambda: ["A1"],
    )


def test_spreadsheet_get_cells_observed_without_native_mutation():
    events: list[str] = []
    document = FakeDocument(events)
    document.objects["Sheet1"] = _sheet()
    collab, _api = collaborators(document, events)
    cell_row = {"address": "A1", "alias": None, "contents": "42", "value": "42"}
    with patch.object(spreadsheet_cell_ops, "read_spreadsheet_cell", return_value=cell_row):
        result = run_spreadsheet_get_cells(collab, "Doc", "Sheet1", ["A1"])

    assert result["success"] is True
    assert result["outcome"] == "observed"
    assert result["sheet"] == "Sheet1"
    assert result["cells"] == [cell_row]
    assert "commit" not in events


def test_missing_document_is_rejected():
    events: list[str] = []
    collab, _api = collaborators(None, events)
    result = run_spreadsheet_get_cells(collab, "Doc", "Sheet1", ["A1"])
    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def test_missing_sheet_is_rejected():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)
    result = run_spreadsheet_get_cells(collab, "Doc", "Sheet1", ["A1"])
    assert result["success"] is False
    assert result["error_code"] == "OBJECT_NOT_FOUND"


def test_spreadsheet_get_cells_has_typed_rpc_handler():
    assert subject.TYPED_RPC_HANDLER[0] == "spreadsheet_get_cells"
    assert callable(subject.TYPED_RPC_HANDLER[1])
