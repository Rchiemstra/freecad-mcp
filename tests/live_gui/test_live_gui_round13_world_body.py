"""Round 13 nested Body world placement regression."""
import pytest
from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui

@pytest.mark.parametrize("nested", [False, "before_pad", "after_pad"],
                         ids=["happy_unplaced", "defect_nested_placed", "happy_move_after_pad"])
def test_body_world_metrics(mcp, gui_log, nested):
    doc = "R13BodyWorld" + str(nested).replace("_", "")
    assert_ok(mcp.call("create_document", name=doc))
    try:
        if nested:
            assert_ok(mcp.call("create_part_container", doc_name=doc, part_name="OuterPart"))
        assert_ok(mcp.call("body_create", doc_name=doc, body_name="Body"))
        if nested == "before_pad":
            assert_ok(mcp.call("move_object", doc_name=doc, obj_name="Body", target_container="OuterPart"))
        assert_ok(mcp.call("sketch_create", doc_name=doc, sketch_name="Sketch", body_name="Body", attach_to="XY_Plane"))
        assert_ok(mcp.call("sketch_add_rectangle", doc_name=doc, sketch_name="Sketch", x1=0, y1=0, x2=10, y2=10))
        assert_ok(mcp.call("pad_feature", doc_name=doc, sketch_name="Sketch", pad_name="Pad", length=5, body_name="Body", strict=True))
        if nested:
            if nested == "after_pad":
                assert_ok(mcp.call("move_object", doc_name=doc, obj_name="Body", target_container="OuterPart"))
            assert_ok(mcp.call("translate", doc_name=doc, obj_name="OuterPart", dx=100, dy=0, dz=0))
            assert_ok(mcp.call("translate", doc_name=doc, obj_name="Body", dx=0, dy=20, dz=0))
        x, y = (100, 20) if nested else (0, 0)
        summary = _payload(assert_ok(mcp.call("get_global_shape", doc_name=doc, obj_name="Body")))
        bbox = _payload(assert_ok(mcp.call("bounding_box", doc_name=doc, obj_name="Body")))
        center = _payload(assert_ok(mcp.call("center_of_mass", doc_name=doc, obj_name="Body")))
        assert summary["center_of_mass"] == pytest.approx([x+5, y+5, 2.5])
        assert [summary["bbox"][k] for k in ("xmin", "ymin", "zmin", "xmax", "ymax", "zmax")] == pytest.approx([x, y, 0, x+10, y+10, 5])
        assert bbox["ymin"] == pytest.approx(y), bbox
        assert [center[k] for k in ("x", "y", "z")] == pytest.approx([x+5, y+5, 2.5])
        assert_ok(mcp.call("execute_code", document=doc, execution_mode="gui", recompute="none",
                           code=f"import FreeCAD as App\nb = App.getDocument('{doc}').Body\nassert App.getDocument('{doc}').Sketch.AttachmentSupport[0][0] in b.Origin.OriginFeatures"))
    finally:
        assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)
