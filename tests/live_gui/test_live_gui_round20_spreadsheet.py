"""Round 20: spreadsheet history restores inputs and aliases silently."""

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui

CELLS = [
    {"address": "A1", "value": 40, "alias": "Len"},
    {"address": "A2", "value": 8, "alias": "PadH"},
    {"address": "A3", "value": "5 deg", "alias": "BadAngle"},
]


def _cells(mcp, doc):
    return _payload(assert_ok(mcp.call(
        "spreadsheet_get_cells", doc_name=doc, sheet_name="Dims",
        addresses=[cell["address"] for cell in CELLS],
    )))["cells"]


def test_round20_spreadsheet_set_cells(mcp, gui_log):
    doc = "R20SheetHappy"
    assert_ok(mcp.call("create_document", name=doc))
    try:
        assert_ok(mcp.call("spreadsheet_create", doc_name=doc, sheet_name="Dims"))
        assert_ok(mcp.call("spreadsheet_set_cells", doc_name=doc, sheet_name="Dims", cells=CELLS))
        result = _cells(mcp, doc)
        assert [cell["alias"] for cell in result] == [cell["alias"] for cell in CELLS]
        assert [cell["contents"] for cell in result] == ["40", "8", "=5 deg"]
    finally:
        assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)


def test_round20_spreadsheet_set_cells_undo_redo(mcp, gui_log):
    doc = "R20SheetHistory"
    assert_ok(mcp.call("create_document", name=doc))
    try:
        assert_ok(mcp.call("spreadsheet_create", doc_name=doc, sheet_name="Dims"))
        original = _cells(mcp, doc)
        assert_ok(mcp.call("spreadsheet_set_cells", doc_name=doc, sheet_name="Dims", cells=CELLS))
        populated = _cells(mcp, doc)
        assert populated != original
        for cycle in range(2):
            assert_ok(mcp.call("undo", doc_name=doc))
            assert _cells(mcp, doc) == original
            assert_clean(gui_log)
            assert_ok(mcp.call("redo", doc_name=doc))
            assert _cells(mcp, doc) == populated
            assert_clean(gui_log)
    finally:
        assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)
