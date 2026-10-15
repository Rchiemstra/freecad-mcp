"""Round 24: delete a settled external spreadsheet source."""
import pytest
from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


@pytest.mark.parametrize("bind", [False, True, "active", "native"], ids=["happy_unbound", "exact_cleared_binding", "defect_active_binding", "native_active_binding"])
def test_round24_delete_source(mcp, gui_log, live_gui, bind):
    opened = []
    try:
        for doc in ("DelSrc", "DelDep"):
            assert_ok(mcp.call("create_document", name=doc))
            opened.append(doc)
        assert_ok(mcp.call("spreadsheet_create", doc_name="DelSrc", sheet_name="Dims"))
        assert_ok(mcp.call("spreadsheet_set_cells", doc_name="DelSrc", sheet_name="Dims",
                           cells=[{"address": "A1", "value": 10, "alias": "PadLen"}]))
        assert_ok(mcp.call("body_create", doc_name="DelDep", body_name="Body"))
        assert_ok(mcp.call("sketch_create", doc_name="DelDep", sketch_name="Sketch", body_name="Body", attach_to="XY_Plane"))
        assert_ok(mcp.call("sketch_add_rectangle", doc_name="DelDep", sketch_name="Sketch", x1=0, y1=0, x2=20, y2=10))
        assert_ok(mcp.call("save_document_as", selector={"document_name": "DelSrc"},
                           destination=str(live_gui.workdir / "r24_DelSrc.FCStd"), overwrite=True))
        assert_ok(mcp.call("pad_feature", doc_name="DelDep", sketch_name="Sketch", pad_name="Pad", length=10, body_name="Body", strict=True))
        assert_ok(mcp.call("save_document_as", selector={"document_name": "DelDep"},
                           destination=str(live_gui.workdir / "r24_DelDep.FCStd"), overwrite=True))
        if bind:
            assert_ok(mcp.call("set_expression", doc_name="DelDep", object_name="Pad", prop_path="Length", expression="DelSrc#<<Dims>>.PadLen"))
        if bind is True:
            assert_ok(mcp.call("clear_expression", doc_name="DelDep", object_name="Pad", prop_path="Length"))
        if bind not in ("active", "native"):
            assert_ok(mcp.call("close_document", doc_name="DelDep"))
            opened.remove("DelDep")
        if bind == "native":
            assert_ok(mcp.call("execute_code", document="DelSrc", recompute="none",
                               code="import FreeCAD as App\nApp.getDocument('DelSrc').removeObject('Dims')"))
        else:
            deleted = _payload(assert_ok(mcp.call("delete_object", doc_name="DelSrc", obj_name="Dims", force=True)))
            assert deleted["deleted"] == ["Dims"], deleted
        if bind in ("active", "native"):
            result = mcp.call("recompute_document", doc_name="DelDep")
            assert not result.ok, result.text
            assert "Dims" in result.text, result.text
            assert_ok(mcp.call("clear_expression", doc_name="DelDep", object_name="Pad", prop_path="Length"))
            assert_ok(mcp.call("edit_object", doc_name="DelDep", obj_name="Pad", obj_properties={"Length": 12}))
        objects = _payload(assert_ok(mcp.call("get_objects", doc_name="DelSrc")))
        assert "Dims" not in str(objects), objects
    finally:
        for doc in reversed(opened):
            assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log, r".*(not found|Invalid object|failed to recompute|unresolved cross-document|document recompute|Error in expression).*")
