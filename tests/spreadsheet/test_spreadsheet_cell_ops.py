"""GUI spreadsheet cell helpers must echo committed aliases."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.spreadsheet import (
    spreadsheet_set_cells_gui,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.spreadsheet_cell_ops import (
    apply_spreadsheet_cell,
    read_spreadsheet_cell,
)

pytestmark = pytest.mark.unit


class _Sheet:
    def __init__(self) -> None:
        self.Name = "Dims"
        self._values: dict[str, str] = {}
        self._aliases: dict[str, str] = {}

    def set(self, address, value):
        self._values[str(address)] = str(value)

    def setAlias(self, address, alias):
        address = str(address)
        alias = str(alias)
        for bound_address, bound_alias in list(self._aliases.items()):
            if bound_alias == alias and bound_address != address:
                del self._aliases[bound_address]
        self._aliases[address] = alias

    def get(self, address):
        return self._values.get(str(address), "")

    def getContents(self, address):
        return self._values.get(str(address), "")

    def getAlias(self, address):
        return self._aliases.get(str(address))

    def getCellFromAlias(self, alias):
        alias = str(alias)
        for address, bound_alias in self._aliases.items():
            if bound_alias == alias:
                return address
        return None


def test_read_spreadsheet_cell_uses_committed_alias():
    sheet = _Sheet()
    sheet.setAlias("B1", "plate_len")
    row = read_spreadsheet_cell(sheet, {"address": "B1"})
    assert row["alias"] == "plate_len"


def test_apply_spreadsheet_cell_does_not_echo_request_alias():
    sheet = _Sheet()
    row, error = apply_spreadsheet_cell(
        sheet,
        {"address": "B1", "value": 40, "set_alias": "plate_len"},
    )
    assert error is None
    assert row == {"address": "B1"}
    assert "alias" not in row


def test_spreadsheet_set_cells_gui_returns_committed_aliases():
    sheet = _Sheet()
    doc = SimpleNamespace(
        getObject=lambda name: sheet if name == "Dims" else None,
        recompute=lambda: None,
    )
    freecad = SimpleNamespace(getDocument=lambda _name: doc)
    result = spreadsheet_set_cells_gui(
        "Doc",
        "Dims",
        [{"address": "B1", "value": 40, "set_alias": "plate_len"}],
        freecad=freecad,
    )
    assert isinstance(result, dict)
    assert result["updated"][0]["alias"] == "plate_len"
