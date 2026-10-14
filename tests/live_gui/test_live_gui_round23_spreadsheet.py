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


def test_round23_existing_cell_external_formula_with_skip_recompute(mcp, gui_log, live_gui):
    opened = []
    try:
        for doc, sheet in (("SrcDoc", "Dims"), ("MidDoc", "Bridge")):
            assert_ok(mcp.call("create_document", name=doc))
            opened.append(doc)
            assert_ok(mcp.call("spreadsheet_create", doc_name=doc, sheet_name=sheet))
            _save(mcp, live_gui, doc)
        assert_ok(mcp.call("spreadsheet_set_cells", doc_name="SrcDoc", sheet_name="Dims",
                           cells=[{"address": "A1", "value": 25, "alias": "PadLen"}]))
        initial = _payload(assert_ok(mcp.call("spreadsheet_set_cells", doc_name="MidDoc", sheet_name="Bridge",
                                              cells=[{"address": "B1", "value": 7}])))
        assert float(initial["updated"][0]["value"]) == pytest.approx(7), initial
        # RecomputesFrozen sets Document::SkipRecompute through the Python API.
        assert_ok(mcp.call("execute_code", document="MidDoc", recompute="none", execution_mode="gui",
                           code="FreeCAD.getDocument('MidDoc').RecomputesFrozen = True"))
        formula = "=SrcDoc#<<Dims>>.PadLen"
        result = _payload(assert_ok(mcp.call("spreadsheet_set_cells", doc_name="MidDoc", sheet_name="Bridge",
                                             cells=[{"address": "B1", "value": formula}])))
        # Check the mutation response before another RPC can settle dirty work.
        assert float(result["updated"][0]["value"]) == pytest.approx(25), result
        cells = _payload(assert_ok(mcp.call("spreadsheet_get_cells", doc_name="MidDoc", sheet_name="Bridge", addresses=["B1"])))
        assert cells["cells"][0]["contents"] == formula, cells
        assert float(cells["cells"][0]["value"]) == pytest.approx(25), cells
        assert_ok(mcp.call("execute_code", document="MidDoc", recompute="none", execution_mode="gui",
                           code="doc = FreeCAD.getDocument('MidDoc')\nassert doc.RecomputesFrozen\nassert 'Touched' not in doc.Bridge.State\nassert not doc.Bridge.MustExecute"))
    finally:
        for doc in reversed(opened):
            assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log, "unresolved cross-document dependency")
