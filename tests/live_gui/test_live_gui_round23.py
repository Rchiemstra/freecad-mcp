"""Round 23: repair a dependent after closing its external expression source."""
import pytest
from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


def _save(mcp, live_gui, doc):
    assert_ok(mcp.call("save_document_as", selector={"document_name": doc},
                       destination=str(live_gui.workdir / ("r23_" + doc + ".FCStd")), overwrite=True))


def _pad(mcp, doc, body, sketch, pad, width, height):
    assert_ok(mcp.call("body_create", doc_name=doc, body_name=body))
    assert_ok(mcp.call("sketch_create", doc_name=doc, sketch_name=sketch, body_name=body, attach_to="XY_Plane"))
    assert_ok(mcp.call("sketch_add_rectangle", doc_name=doc, sketch_name=sketch, x1=0, y1=0, x2=width, y2=height))
    assert_ok(mcp.call("pad_feature", doc_name=doc, sketch_name=sketch, pad_name=pad, length=10, body_name=body, strict=True))


@pytest.mark.parametrize("close_source", [False, True], ids=["happy_open_source", "defect_closed_source"])
def test_round23_closed_source_repair(mcp, gui_log, live_gui, close_source):
    opened = []
    try:
        for doc in ("SrcDoc", "MidDoc", "DepDoc"):
            assert_ok(mcp.call("create_document", name=doc))
            opened.append(doc)
            if doc == "SrcDoc":
                assert_ok(mcp.call("spreadsheet_create", doc_name=doc, sheet_name="Dims"))
                assert_ok(mcp.call("spreadsheet_set_cells", doc_name=doc, sheet_name="Dims",
                                   cells=[{"address": "A1", "value": 15, "alias": "PadLen"}]))
            elif doc == "MidDoc":
                _pad(mcp, doc, "MidBody", "MidSketch", "MidPad", 10, 10)
            else:
                _pad(mcp, doc, "Body", "Sketch", "Pad", 40, 20)
            _save(mcp, live_gui, doc)
            if doc != "SrcDoc":
                assert_ok(mcp.call("set_expression", doc_name=doc, object_name="MidPad" if doc == "MidDoc" else "Pad",
                                   prop_path="Length", expression="SrcDoc#<<Dims>>.PadLen" if doc == "MidDoc" else "MidDoc#MidPad.Length"))
        if close_source:
            assert_ok(mcp.call("close_document", doc_name="MidDoc"))
            opened.remove("MidDoc")
            result = mcp.call("recompute_document", doc_name="DepDoc")
            assert not result.ok, result.text
            assert "MidDoc" in result.text and "not found" in result.text, result.text
        else:
            assert_ok(mcp.call("recompute_document", doc_name="DepDoc"))
        # An edit which needs the missing source must fail without fencing repair.
        edit = mcp.call("edit_object", doc_name="DepDoc", obj_name="Pad", obj_properties={"Length": 12})
        if close_source:
            assert not edit.ok, edit.text
            assert "persistent recompute failure" not in edit.text, edit.text
            assert "quarantined" not in edit.text, edit.text
        else:
            assert not edit.ok, edit.text
            assert "did not keep the assigned value" in edit.text, edit.text
        assert_ok(mcp.call("clear_expression", doc_name="DepDoc", object_name="Pad", prop_path="Length"))
        assert_ok(mcp.call("edit_object", doc_name="DepDoc", obj_name="Pad", obj_properties={"Length": 12}))
        assert_ok(mcp.call("set_expression", doc_name="DepDoc", object_name="Pad", prop_path="Length", expression="SrcDoc#<<Dims>>.PadLen"))
        volume = _payload(assert_ok(mcp.call("measure_volume", doc_name="DepDoc", obj_name="Pad")))
        assert volume["volume_mm3"] == pytest.approx(12000)
    finally:
        for doc in reversed(opened):
            assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log, r".*(not found|Invalid object|failed to recompute|unresolved cross-document|document recompute|Error in expression).*")


