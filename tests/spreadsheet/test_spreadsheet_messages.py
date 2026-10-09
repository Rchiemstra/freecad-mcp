"""Spreadsheet refusals and reads must describe what actually happened.

Re-aliasing a cell whose alias formulas use said "'A1' is read-only", and
reading an empty cell gave value_error "Invalid cell address or property: A1".
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import spreadsheet_set_alias
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.spreadsheet_cell_ops import (
    read_spreadsheet_cell,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.spreadsheet_set_alias import (
    SpreadsheetSetAliasError,
)

pytestmark = pytest.mark.unit


def _sheet(**overrides):
    def get(address):
        raise ValueError(f"Invalid cell address or property: {address}")

    sheet = SimpleNamespace(
        Name="Dims",
        getAlias=lambda address: None,
        getContents=lambda address: "",
        get=get,
        setAlias=lambda address, alias: None,
        getPropertyStatus=lambda name: [],
    )
    for key, value in overrides.items():
        setattr(sheet, key, value)
    return sheet


def test_an_empty_cell_reads_as_empty():
    row = read_spreadsheet_cell(_sheet(), "A1")

    assert row["value"] is None
    assert row["empty"] is True
    assert "value_error" not in row


def test_a_failing_formula_still_reports_its_error():
    row = read_spreadsheet_cell(_sheet(getContents=lambda address: "=1/0"), "A1")

    assert "value_error" in row


def test_re_aliasing_a_referenced_alias_names_the_alias():
    sheet = _sheet(
        getAlias=lambda address: "Width",
        isReadOnly=lambda name: True,
    )
    document = SimpleNamespace(getObject={"Dims": sheet}.get)
    request = SimpleNamespace(sheet_name="Dims", address="A1", alias="WidthRenamed")

    with pytest.raises(SpreadsheetSetAliasError) as caught:
        spreadsheet_set_alias.apply_spreadsheet_set_alias(document, request)

    assert "'Width'" in str(caught.value) and "expressions" in str(caught.value)
