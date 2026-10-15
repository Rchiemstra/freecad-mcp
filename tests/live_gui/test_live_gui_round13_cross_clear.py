"""Round 13 cross-document expression removal."""
import pytest
from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


@pytest.mark.parametrize("cross_document", [False, True], ids=["happy_same_doc", "defect_cross_doc"])
def test_clear_length_binding_across_documents(mcp, gui_log, live_gui, cross_document):
    source, target = "R13ClearSource", "R13ClearTarget"
    for doc in (source, target):
        assert_ok(mcp.call("create_document", name=doc))
    try:
        for doc in (source, target):
            assert_ok(mcp.call("spreadsheet_create", doc_name=doc, sheet_name="Dims"))
            assert_ok(mcp.call("spreadsheet_set_cells", doc_name=doc, sheet_name="Dims",
                               cells=[{"address": "A1", "value": 25, "alias": "PadH"},
                                      {"address": "A2", "value": 10, "alias": "Width"}]))
        assert_ok(mcp.call("body_create", doc_name=target, body_name="Body"))
        assert_ok(mcp.call("sketch_create", doc_name=target, sketch_name="Sketch", body_name="Body", attach_to="XY_Plane"))
        assert_ok(mcp.call("sketch_add_rectangle", doc_name=target, sketch_name="Sketch", x1=0, y1=0, x2=10, y2=10))
        assert_ok(mcp.call("sketch_constrain_distance", doc_name=target, sketch_name="Sketch", geo=0, value=10, name="WidthDim"))
        assert_ok(mcp.call("pad_feature", doc_name=target, sketch_name="Sketch", pad_name="Pad", length=5, body_name="Body", strict=True))
        for doc in (source, target):
            assert_ok(mcp.call("save_document_as", selector={"document_name": doc},
                               destination=str(live_gui.workdir / (doc + ".FCStd")), overwrite=True))
        # Round 13 also had cross-document constraint bindings. Clearing
        # Length must work even while its profile retains an external binding.
        width_expression = source + "#Dims.Width" if cross_document else "Dims.Width"
        assert_ok(mcp.call("set_expression", doc_name=target, object_name="Sketch",
                           prop_path="Constraints.WidthDim", expression=width_expression))
        expression = source + "#Dims.PadH" if cross_document else "Dims.PadH"
        assert_ok(mcp.call("set_expression", doc_name=target, object_name="Pad", prop_path="Length", expression=expression))
        for doc in (source, target):
            assert_ok(mcp.call("recompute_document", doc_name=doc))
        result = _payload(assert_ok(mcp.call("clear_expression", doc_name=target, object_name="Pad", prop_path="Length")))
        assert result["committed"] is True
        expressions = _payload(assert_ok(mcp.call("list_expressions", doc_name=target, object_name="Pad")))
        assert "PadH" not in str(expressions)
        profile_bindings = _payload(assert_ok(mcp.call("list_expressions", doc_name=target, object_name="Sketch")))
        assert "Dims.Width" in str(profile_bindings), profile_bindings
        feeding_doc = source if cross_document else target
        assert_ok(mcp.call("spreadsheet_set_cells", doc_name=feeding_doc, sheet_name="Dims", cells=[{"address": "A1", "value": 30}]))
        assert_ok(mcp.call("recompute_document", doc_name=target))
        volume = _payload(assert_ok(mcp.call("measure_volume", doc_name=target, obj_name="Pad")))
        assert volume["volume_mm3"] == pytest.approx(2500)
    finally:
        assert_ok(mcp.call("close_document", doc_name=target))
        assert_ok(mcp.call("close_document", doc_name=source))
    assert_clean(gui_log, "unresolved cross-document dependency")
