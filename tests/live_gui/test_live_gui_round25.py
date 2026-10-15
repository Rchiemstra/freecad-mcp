"""Round 25: saved Pad and spreadsheet bindings survive source lifecycle changes."""
import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload
from tests.live_gui.test_live_gui_round23 import _pad

pytestmark = pytest.mark.live_gui


def _setup(mcp, live_gui, opened, bind=True):
    for doc in ("SrcDoc", "DepDoc"):
        assert_ok(mcp.call("create_document", name=doc))
        opened.append(doc)
    assert_ok(mcp.call("spreadsheet_create", doc_name="SrcDoc", sheet_name="Dims"))
    assert_ok(mcp.call("spreadsheet_set_cells", doc_name="SrcDoc", sheet_name="Dims",
                       cells=[{"address": "A1", "value": 12, "alias": "PadLen"}]))
    _pad(mcp, "DepDoc", "Body", "Sketch", "Pad", 20, 10)
    assert_ok(mcp.call("spreadsheet_create", doc_name="DepDoc", sheet_name="Bridge"))
    for doc in opened:
        assert_ok(mcp.call("save_document_as", selector={"document_name": doc},
                           destination=str(live_gui.workdir / (doc + ".FCStd")), overwrite=True))
    if bind:
        bound = _payload(assert_ok(mcp.call("set_expression", doc_name="DepDoc", object_name="Pad",
                                           prop_path="Length", expression="SrcDoc#<<Dims>>.PadLen")))
        assert "12" in str(bound), bound
    assert_ok(mcp.call("spreadsheet_set_cells", doc_name="DepDoc", sheet_name="Bridge",
                       cells=[{"address": "A1", "value": "=SrcDoc#<<Dims>>.PadLen" if bind else 12}]))
    for doc in opened:
        assert_ok(mcp.call("save_document_as", selector={"document_name": doc},
                           destination=str(live_gui.workdir / (doc + ".FCStd")), overwrite=True))


def _check_value(mcp, value):
    cells = _payload(assert_ok(mcp.call("spreadsheet_get_cells", doc_name="DepDoc",
                                       sheet_name="Bridge", addresses=["A1"])))
    assert float(cells["cells"][0]["value"]) == pytest.approx(value), cells
    volume = _payload(assert_ok(mcp.call("measure_volume", doc_name="DepDoc", obj_name="Pad")))
    assert volume["volume_mm3"] == pytest.approx(200 * value), volume


@pytest.mark.parametrize("mode", ["unbound", "force", "native"], ids=["happy_unbound", "defect_force", "defect_native"])
def test_round25_delete_source(mcp, gui_log, live_gui, mode):
    opened = []
    try:
        _setup(mcp, live_gui, opened, bind=mode != "unbound")
        if mode != "unbound":
            refusal = mcp.call("delete_object", doc_name="SrcDoc", obj_name="Dims", force=False)
            assert not refusal.ok, refusal.text
            assert "depend" in refusal.text.lower(), refusal.text
        if mode == "native":
            assert_ok(mcp.call("execute_code", document="SrcDoc", recompute="none",
                               code="FreeCAD.getDocument('SrcDoc').removeObject('Dims')"))
        else:
            deleted = _payload(assert_ok(mcp.call("delete_object", doc_name="SrcDoc", obj_name="Dims", force=True)))
            assert deleted["deleted"] == ["Dims"], deleted
        objects = _payload(assert_ok(mcp.call("get_objects", doc_name="SrcDoc")))
        assert "Dims" not in str(objects), objects
        if mode != "unbound":
            failed = mcp.call("recompute_document", doc_name="DepDoc")
            assert not failed.ok and "Dims" in failed.text, failed.text
            assert "pending recompute work outside" not in failed.text, failed.text
            assert_ok(mcp.call("undo", doc_name="SrcDoc"))
            assert_ok(mcp.call("recompute_document", doc_name="DepDoc"))
            _check_value(mcp, 12)
            assert_ok(mcp.call("redo", doc_name="SrcDoc"))
            assert "Dims" not in str(_payload(assert_ok(mcp.call("get_objects", doc_name="SrcDoc"))))
            assert_ok(mcp.call("undo", doc_name="SrcDoc"))
            assert_ok(mcp.call("spreadsheet_set_cells", doc_name="SrcDoc", sheet_name="Dims",
                               cells=[{"address": "A1", "value": 18}]))
            assert_ok(mcp.call("recompute_document", doc_name="DepDoc"))
            _check_value(mcp, 18)
            assert_ok(mcp.call("delete_object", doc_name="SrcDoc", obj_name="Dims", force=True))
            assert_ok(mcp.call("clear_expression", doc_name="DepDoc", object_name="Pad", prop_path="Length"))
            assert_ok(mcp.call("spreadsheet_set_cells", doc_name="DepDoc", sheet_name="Bridge",
                               cells=[{"address": "A1", "value": 12}]))
            assert_ok(mcp.call("edit_object", doc_name="DepDoc", obj_name="Pad", obj_properties={"Length": 12}))
    finally:
        for doc in reversed(opened):
            assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log, r".*(not found|Invalid object|failed to recompute|unresolved cross-document|document recompute|Error in expression|Unresolved dependency|Cells with errors).*")


@pytest.mark.parametrize("close_source", [False, True, "reopened"],
                         ids=["happy_open", "defect_closed", "defect_reopened_dependent"])
def test_round25_close_source_repair(mcp, gui_log, live_gui, close_source):
    opened = []
    try:
        _setup(mcp, live_gui, opened)
        if close_source:
            assert_ok(mcp.call("close_document", doc_name="SrcDoc"))
            opened.remove("SrcDoc")
            if close_source == "reopened":
                assert_ok(mcp.call("close_document", doc_name="DepDoc"))
                opened.remove("DepDoc")
                assert_ok(mcp.call("open_document", path=str(live_gui.workdir / "DepDoc.FCStd")))
                opened.append("DepDoc")
                # Restore may reopen a persisted external file. Test the
                # missing-source boundary again with that source closed.
                docs = _payload(assert_ok(mcp.call("list_documents")))
                if "SrcDoc" in str(docs):
                    assert_ok(mcp.call("close_document", doc_name="SrcDoc"))
            failed = mcp.call("recompute_document", doc_name="DepDoc")
            assert not failed.ok and "SrcDoc" in failed.text and "not found" in failed.text, failed.text
            assert "pending recompute work outside" not in failed.text, failed.text
            waited = mcp.call("recompute_and_wait", doc_name="DepDoc")
            assert not waited.ok and "SrcDoc" in waited.text, waited.text
            assert "pending recompute work outside" not in waited.text, waited.text
        else:
            assert_ok(mcp.call("recompute_document", doc_name="DepDoc"))
        assert_ok(mcp.call("clear_expression", doc_name="DepDoc", object_name="Pad", prop_path="Length"))
        assert_ok(mcp.call("translate", doc_name="DepDoc", obj_name="Body", dx=1, dy=0, dz=0))
        assert_ok(mcp.call("edit_object", doc_name="DepDoc", obj_name="Pad", obj_properties={"Length": 21}))
        assert_ok(mcp.call("spreadsheet_set_cells", doc_name="DepDoc", sheet_name="Bridge",
                           cells=[{"address": "A1", "value": 21}]))
        _check_value(mcp, 21)
        if close_source:
            assert_ok(mcp.call("open_document", path=str(live_gui.workdir / "SrcDoc.FCStd")))
            opened.append("SrcDoc")
        assert_ok(mcp.call("set_expression", doc_name="DepDoc", object_name="Pad", prop_path="Length",
                           expression="SrcDoc#<<Dims>>.PadLen"))
        assert_ok(mcp.call("spreadsheet_set_cells", doc_name="DepDoc", sheet_name="Bridge",
                           cells=[{"address": "A1", "value": "=SrcDoc#<<Dims>>.PadLen"}]))
        _check_value(mcp, 12)
    finally:
        for doc in reversed(opened):
            assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log, r".*(not found|Invalid object|failed to recompute|unresolved cross-document|document recompute|Error in expression|Cells with errors).*")
