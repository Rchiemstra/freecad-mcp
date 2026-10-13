"""Round 13 expression removal regression tests."""
import pytest
from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui

@pytest.mark.parametrize("path", ["Length", "Constraints.LenDim", "Constraints[0]", ".Constraints.LenDim"],
                         ids=["happy_length", "defect_named", "defect_index", "defect_dotted"])
def test_clear_local_binding(mcp, gui_log, path):
    doc = "R13ClearLocal"
    assert_ok(mcp.call("create_document", name=doc))
    try:
        assert_ok(mcp.call("spreadsheet_create", doc_name=doc, sheet_name="Dims"))
        assert_ok(mcp.call("spreadsheet_set_cells", doc_name=doc, sheet_name="Dims",
                           cells=[{"address": "A1", "value": 12, "alias": "PadLen"}]))
        if path == "Length":
            obj = "Box"
            assert_ok(mcp.call("create_object", doc_name=doc, obj_name=obj, obj_type="Part::Box"))
        else:
            obj = "Sketch"
            assert_ok(mcp.call("sketch_create", doc_name=doc, sketch_name=obj))
            assert_ok(mcp.call("sketch_add_line", doc_name=doc, sketch_name=obj, x1=0, y1=0, x2=30, y2=0))
            assert_ok(mcp.call("sketch_constrain_distance", doc_name=doc, sketch_name=obj, geo=0, value=30, name="LenDim"))
        assert_ok(mcp.call("set_expression", doc_name=doc, object_name=obj, prop_path=path, expression="<<Dims>>.PadLen"))
        before = _payload(assert_ok(mcp.call("list_expressions", doc_name=doc, object_name=obj)))
        assert "PadLen" in str(before)
        cleared = _payload(assert_ok(mcp.call("clear_expression", doc_name=doc, object_name=obj, prop_path=path)))
        assert cleared["committed"] is True
        after = _payload(assert_ok(mcp.call("list_expressions", doc_name=doc, object_name=obj)))
        assert "PadLen" not in str(after), after
        assert_ok(mcp.call("spreadsheet_set_cells", doc_name=doc, sheet_name="Dims", cells=[{"address": "A1", "value": 17}]))
        # Confirm that clearing keeps the last value and removes the dependency.
        result = assert_ok(mcp.call("execute_code", document=doc, execution_mode="gui", recompute="none",
                                   code=f"import FreeCAD as App\no = App.getDocument('{doc}').getObject('{obj}')\nprint('RETAINED', o.Length.Value if '{obj}' == 'Box' else o.getDatum(0).Value)"))
        assert "RETAINED 12" in result.text, result.text
    finally:
        assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)
