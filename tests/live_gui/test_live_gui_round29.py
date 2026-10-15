"""Round 29: component units and incremental missing-source repair."""
import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload
from tests.live_gui.test_live_gui_round28 import _setup, _width

pytestmark = pytest.mark.live_gui


@pytest.mark.parametrize("expression,accepted", [("2mm", True), ("1deg", False)],
                         ids=["happy_length", "defect_angle"])
def test_round29_placement_units(mcp, gui_log, expression, accepted):
    assert_ok(mcp.call("create_document", name="UDoc"))
    try:
        assert_ok(mcp.call("create_object", doc_name="UDoc", obj_type="Part::Box", obj_name="B",
                           obj_properties={"Length": 4, "Width": 4, "Height": 4}))
        result = mcp.call("set_expression", doc_name="UDoc", object_name="B",
                          prop_path="Placement.Base.y", expression=expression)
        if accepted:
            assert_ok(result)
        else:
            assert result.is_error, result
            assert "EXPRESSION_UNIT_MISMATCH" in str(result), result
        bindings = _payload(assert_ok(mcp.call("list_expressions", doc_name="UDoc", object_name="B")))
        assert bindings["count"] == int(accepted), bindings
        assert_ok(mcp.call("execute_code", document="UDoc", recompute="none",
                           code="assert FreeCAD.getDocument('UDoc').B.Placement.Base.y == " + str(2 if accepted else 0)))
    finally:
        assert_ok(mcp.call("close_document", doc_name="UDoc"))
    assert_clean(gui_log)


@pytest.mark.parametrize("mode", ["open", "clear", "edit"],
                         ids=["happy_open", "defect_second_clear", "defect_typed_edit"])
def test_round29_incremental_source_repair(mcp, gui_log, live_gui, mode):
    opened = []
    try:
        _setup(mcp, live_gui, opened)
        assert_ok(mcp.call("set_expression", doc_name="DepDoc", object_name="Sketch",
                           prop_path="Constraints.H", expression="SrcDoc#<<Dims>>.Wall / 2"))
        assert_ok(mcp.call("save_document", selector={"document_name": "DepDoc"}))
        if mode != "open":
            assert_ok(mcp.call("close_document", doc_name="SrcDoc"))
            opened.remove("SrcDoc")
        assert_ok(mcp.call("clear_expression", doc_name="DepDoc", object_name="Sketch", prop_path="Constraints.W"))
        if mode != "clear":
            assert_ok(mcp.call("undo", doc_name="DepDoc"))
            bindings = _payload(assert_ok(mcp.call("list_expressions", doc_name="DepDoc", object_name="Sketch")))
            assert bindings["count"] == 2, bindings
            assert_ok(mcp.call("clear_expression", doc_name="DepDoc", object_name="Sketch", prop_path="Constraints.W"))
            assert_ok(mcp.call("sketch_edit_constraint", doc_name="DepDoc", sketch_name="Sketch", index=8, value=35))
            _width(mcp, 35)
            assert_ok(mcp.call("undo", doc_name="DepDoc"))
            assert_ok(mcp.call("sketch_edit_constraint", doc_name="DepDoc", sketch_name="Sketch", index=8, value=35))
            _width(mcp, 35)
        assert_ok(mcp.call("clear_expression", doc_name="DepDoc", object_name="Sketch", prop_path="Constraints.H"))
        assert_ok(mcp.call("undo", doc_name="DepDoc"))
        bindings = _payload(assert_ok(mcp.call("list_expressions", doc_name="DepDoc", object_name="Sketch")))
        assert bindings["count"] == 1, bindings
        assert_ok(mcp.call("clear_expression", doc_name="DepDoc", object_name="Sketch", prop_path="Constraints.H"))
        if mode != "open":
            unresolved = mcp.call("recompute_document", doc_name="DepDoc")
            assert not unresolved.ok and "SrcDoc" in unresolved.text, unresolved
            assert "quarantined" not in unresolved.text, unresolved
        assert_ok(mcp.call("clear_expression", doc_name="DepDoc", object_name="Pad", prop_path="Length"))
        assert_ok(mcp.call("recompute_document", doc_name="DepDoc"))
        volume = _payload(assert_ok(mcp.call("measure_volume", doc_name="DepDoc", obj_name="Pad")))
        assert volume["volume_mm3"] == pytest.approx((30 if mode == "clear" else 35) * 15 * 12)
    finally:
        for doc in reversed(opened):
            assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log, r".*(not found|failed to recompute|unresolved cross-document|Error in expression|document recompute).*")


def test_round29_other_length_components(mcp, gui_log):
    assert_ok(mcp.call("create_document", name="UDoc"))
    try:
        assert_ok(mcp.call("execute_code", document="UDoc", recompute="none", execution_mode="gui", code="""
b = FreeCAD.getDocument('UDoc').addObject('Part::Box', 'B')
b.addProperty('App::PropertyVectorDistance', 'Offset')
b.addProperty('App::PropertyPosition', 'Position')
b.addProperty('App::PropertyPlacement', 'Mount')
"""))
        for root in ("Placement.Base", "Offset", "Position", "Mount.Base"):
            for axis in ("x", "y", "z"):
                path = root + "." + axis
                assert_ok(mcp.call("set_expression", doc_name="UDoc", object_name="B", prop_path=path, expression="2mm"))
                failed = mcp.call("set_expression", doc_name="UDoc", object_name="B", prop_path=path, expression="1deg")
                assert failed.is_error and "EXPRESSION_UNIT_MISMATCH" in str(failed), (path, failed)
                bindings = _payload(assert_ok(mcp.call("list_expressions", doc_name="UDoc", object_name="B")))
                assert bindings["count"] == 1 and "2 mm" in str(bindings), bindings
                assert_ok(mcp.call("clear_expression", doc_name="UDoc", object_name="B", prop_path=path))
    finally:
        assert_ok(mcp.call("close_document", doc_name="UDoc"))
    assert_clean(gui_log)
