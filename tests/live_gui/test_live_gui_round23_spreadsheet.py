"""Round 23 external spreadsheet formulas."""
import pytest
from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload
from tests.live_gui.test_live_gui_round23 import _save

pytestmark = pytest.mark.live_gui


@pytest.mark.parametrize("cross_document", [False, True], ids=["happy_local", "defect_external"])
def test_round23_spreadsheet_formula(mcp, gui_log, live_gui, cross_document):
    opened = []
    try:
        for doc in ("SrcDoc", "MidDoc"):
            assert_ok(mcp.call("create_document", name=doc))
            opened.append(doc)
            assert_ok(mcp.call("spreadsheet_create", doc_name=doc, sheet_name="Dims" if doc == "SrcDoc" else "Bridge"))
            if doc == "SrcDoc":
                assert_ok(mcp.call("spreadsheet_set_cells", doc_name=doc, sheet_name="Dims",
                                   cells=[{"address": "A1", "value": 25, "alias": "PadLen"}]))
            _save(mcp, live_gui, doc)
        formula = "=SrcDoc#<<Dims>>.PadLen" if cross_document else "=25"
        assert_ok(mcp.call("spreadsheet_set_cells", doc_name="MidDoc", sheet_name="Bridge",
                           cells=[{"address": "B1", "value": formula, "alias": "BridgedLen"}]))
        cells = _payload(assert_ok(mcp.call("spreadsheet_get_cells", doc_name="MidDoc", sheet_name="Bridge", addresses=["B1"])))
        assert float(cells["cells"][0]["value"]) == pytest.approx(25), cells
        if cross_document:
            assert_ok(mcp.call("spreadsheet_set_cells", doc_name="SrcDoc", sheet_name="Dims", cells=[{"address": "A1", "value": 30}]))
            assert_ok(mcp.call("recompute_document", doc_name="MidDoc"))
            cells = _payload(assert_ok(mcp.call("spreadsheet_get_cells", doc_name="MidDoc", sheet_name="Bridge", addresses=["B1"])))
            assert float(cells["cells"][0]["value"]) == pytest.approx(30), cells
    finally:
        for doc in reversed(opened):
            assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log, "unresolved cross-document dependency")
