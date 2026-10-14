"""Round 21: an existing external expression must not block unrelated edits."""

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


@pytest.mark.parametrize("cross_document", [False, True], ids=["happy_same_doc", "defect_cross_doc"])
def test_round21_unrelated_offset_after_expression(mcp, gui_log, live_gui, cross_document):
    source, target = "R21ExprSource", "R21ExprTarget"
    for doc in (source, target):
        assert_ok(mcp.call("create_document", name=doc))
    try:
        for doc in (source, target):
            assert_ok(mcp.call("spreadsheet_create", doc_name=doc, sheet_name="Dims"))
            assert_ok(mcp.call("spreadsheet_set_cells", doc_name=doc, sheet_name="Dims",
                               cells=[{"address": "A1", "value": 12, "alias": "PadLen"}]))
        assert_ok(mcp.call("body_create", doc_name=target, body_name="Body"))
        assert_ok(mcp.call("sketch_create", doc_name=target, sketch_name="Profile",
                           body_name="Body", attach_to="XY_Plane"))
        assert_ok(mcp.call("sketch_add_rectangle", doc_name=target, sketch_name="Profile",
                           x1=0, y1=0, x2=10, y2=10))
        assert_ok(mcp.call("pad_feature", doc_name=target, sketch_name="Profile",
                           pad_name="Pad", length=5, body_name="Body", strict=True))
        assert_ok(mcp.call("sketch_create", doc_name=target, sketch_name="LooseSketch",
                           body_name="Body", attach_to="XY_Plane"))
        assert_ok(mcp.call("sketch_add_rectangle", doc_name=target, sketch_name="LooseSketch",
                           x1=20, y1=20, x2=30, y2=30))
        for doc in (source, target):
            assert_ok(mcp.call("save_document_as", selector={"document_name": doc},
                               destination=str(live_gui.workdir / (doc + ".FCStd")), overwrite=True))
        expression = source + "#Dims.PadLen" if cross_document else "Dims.PadLen"
        assert_ok(mcp.call("set_expression", doc_name=target, object_name="Pad",
                           prop_path="Length", expression=expression))
        for doc in (source, target):
            assert_ok(mcp.call("recompute_document", doc_name=doc))
        assert_ok(mcp.call("sketch_offset", doc_name=target, sketch_name="LooseSketch",
                           geo_indices=[0, 1, 2, 3], offset=2))
        geometry = _payload(assert_ok(mcp.call("get_sketch_geometry", doc_name=target,
                                              sketch_name="LooseSketch")))
        assert len(geometry["geometry"]) == 8, geometry
        volume = _payload(assert_ok(mcp.call("measure_volume", doc_name=target, obj_name="Pad")))
        assert volume["volume_mm3"] == pytest.approx(1200)
        bindings = _payload(assert_ok(mcp.call("list_expressions", doc_name=target, object_name="Pad")))
        assert expression in str(bindings)
    finally:
        assert_ok(mcp.call("close_document", doc_name=target))
        assert_ok(mcp.call("close_document", doc_name=source))
    assert_clean(gui_log, "unresolved cross-document dependency")
