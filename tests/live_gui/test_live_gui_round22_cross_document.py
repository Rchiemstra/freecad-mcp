"""Round 22: direct external expressions after profile edits."""

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


@pytest.mark.parametrize("cross_document", [False, True], ids=["happy_local", "defect_direct_external"])
def test_round22_profile_offset_direct_expression(mcp, gui_log, live_gui, cross_document):
    source, target = "R22Src", "R22Dep"
    for doc in (source, target):
        assert_ok(mcp.call("create_document", name=doc))
    try:
        sheet_doc = source if cross_document else target
        assert_ok(mcp.call("spreadsheet_create", doc_name=sheet_doc, sheet_name="Dims"))
        assert_ok(mcp.call("spreadsheet_set_cells", doc_name=sheet_doc, sheet_name="Dims",
                           cells=[{"address": "A1", "value": 10, "alias": "PadH"}]))
        for doc, width, height in ((source, 40, 20), (target, 30, 15)):
            assert_ok(mcp.call("body_create", doc_name=doc, body_name="Body"))
            assert_ok(mcp.call("sketch_create", doc_name=doc, sketch_name="Sketch",
                               body_name="Body", attach_to="XY_Plane"))
            assert_ok(mcp.call("sketch_add_rectangle", doc_name=doc, sketch_name="Sketch",
                               x1=0, y1=0, x2=width, y2=height))
            assert_ok(mcp.call("pad_feature", doc_name=doc, sketch_name="Sketch",
                               pad_name="Pad", length=10, body_name="Body", strict=True))
        assert_ok(mcp.call("save_document_as", selector={"document_name": source},
                           destination=str(live_gui.workdir / "R22Src.FCStd"), overwrite=True))
        # Native external-expression links require a saved owner as well.
        assert_ok(mcp.call("save_document_as", selector={"document_name": target},
                           destination=str(live_gui.workdir / "R22Dep.FCStd"), overwrite=True))
        expression = ('R22Src#' if cross_document else '') + '<<Dims>>.PadH'
        assert_ok(mcp.call("set_expression", doc_name=target, object_name="Pad",
                           prop_path="Length", expression=expression))
        for doc in (source, target):
            assert_ok(mcp.call("recompute_document", doc_name=doc))
        assert_ok(mcp.call("sketch_offset", doc_name=target, sketch_name="Sketch",
                           geo_indices=[0, 1, 2, 3], offset=-2, copy=True, construction=True))
        geometry = _payload(assert_ok(mcp.call("get_sketch_geometry", doc_name=target,
                                              sketch_name="Sketch")))
        assert len(geometry["geometry"]) == 8, geometry
        bindings = _payload(assert_ok(mcp.call("list_expressions", doc_name=target, object_name="Pad")))
        assert expression in str(bindings)
        volume = _payload(assert_ok(mcp.call("measure_volume", doc_name=target, obj_name="Pad")))
        assert volume["volume_mm3"] == pytest.approx(4500)
        assert_ok(mcp.call("spreadsheet_set_cells", doc_name=sheet_doc, sheet_name="Dims",
                           cells=[{"address": "A1", "value": 22}]))
        for doc in (source, target):
            assert_ok(mcp.call("recompute_document", doc_name=doc))
        volume = _payload(assert_ok(mcp.call("measure_volume", doc_name=target, obj_name="Pad")))
        assert volume["volume_mm3"] == pytest.approx(9900)
    finally:
        assert_ok(mcp.call("close_document", doc_name=target))
        assert_ok(mcp.call("close_document", doc_name=source))
    assert_clean(gui_log, "unresolved cross-document dependency")
