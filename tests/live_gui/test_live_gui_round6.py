"""Live checks for the defects the sixth agent stress run reported."""

from __future__ import annotations

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _rejected
from tests.live_gui.test_live_gui_stress import _part_body

pytestmark = pytest.mark.live_gui


def test_a_helix_with_millions_of_turns_is_refused(mcp, gui_log):
    """pitch=0.01, height=100000 kept FreeCAD busy for minutes and every later
    call failed."""

    _part_body(mcp, "LiveHelix")
    _rejected(mcp.call("helical_sweep_feature", doc_name="LiveHelix", profile_sketch="Sk",
                       helix_name="Hx", pitch=0.01, height=100000, radius=20,
                       body_name="Body"), "at most 150 turns")
    assert_ok(mcp.call("list_documents"))
    assert_ok(mcp.call("close_document", doc_name="LiveHelix"))
    assert_clean(gui_log)


def test_a_missing_expression_property_leaves_no_object(mcp, gui_log):
    _part_body(mcp, "LiveExprProp")

    _rejected(mcp.call("set_expression", doc_name="LiveExprProp", object_name="Pad",
                       prop_path="NoSuchProperty", expression="1+1"),
              "has no property 'NoSuchProperty'")
    objects = assert_ok(mcp.call("get_objects", doc_name="LiveExprProp"))
    assert "__mcp_expr_" not in objects.text
    assert_ok(mcp.call("close_document", doc_name="LiveExprProp"))
    assert_clean(gui_log)


def test_a_radius_on_a_line_leaves_the_sketch_padable(mcp, gui_log):
    """The rolled-back radius left the sketch reporting a malformed constraint
    and the following pad refused the untouched rectangle."""

    assert_ok(mcp.call("create_document", name="LiveRadius"))
    assert_ok(mcp.call("body_create", doc_name="LiveRadius", body_name="Body"))
    assert_ok(mcp.call("sketch_create", doc_name="LiveRadius", sketch_name="Sk",
                       body_name="Body"))
    assert_ok(mcp.call("sketch_add_rectangle", doc_name="LiveRadius", sketch_name="Sk",
                       x1=0, y1=0, x2=30, y2=20))

    _rejected(mcp.call("sketch_constrain_radius", doc_name="LiveRadius", sketch_name="Sk",
                       geo=0, value=5), "needs a circle or arc")
    assert_ok(mcp.call("pad_feature", doc_name="LiveRadius", sketch_name="Sk",
                       pad_name="Pad", length=5, body_name="Body"))
    assert_ok(mcp.call("close_document", doc_name="LiveRadius"))
    assert_clean(gui_log)


def test_a_negative_datum_through_a_spreadsheet_is_refused_quietly(mcp, gui_log):
    """Driving a Distance negative made the solver print "Both points are
    equal" before the change was rolled back."""

    _part_body(mcp, "LiveExprDatum")
    assert_ok(mcp.call("sketch_constrain_distance", doc_name="LiveExprDatum", sketch_name="Sk",
                       geo=0, value=20, name="Width"))
    assert_ok(mcp.call("spreadsheet_create", doc_name="LiveExprDatum", sheet_name="Dims"))
    assert_ok(mcp.call("spreadsheet_set_cells", doc_name="LiveExprDatum", sheet_name="Dims",
                       cells=[{"address": "A1", "value": -5, "alias": "Neg"},
                              {"address": "A2", "value": 20, "alias": "Same"}]))

    _rejected(mcp.call("set_expression", doc_name="LiveExprDatum", object_name="Sk",
                       prop_path=".Constraints.Width", expression="<<Dims>>.Neg"),
              "must be > 0")
    assert_ok(mcp.call("set_expression", doc_name="LiveExprDatum", object_name="Sk",
                       prop_path=".Constraints.Width", expression="<<Dims>>.Same"))
    assert_ok(mcp.call("close_document", doc_name="LiveExprDatum"))
    assert_clean(gui_log)


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("boolean_union", {"shape1": "CylA", "shape2": "CylA", "result_name": "Self"}),
        ("boolean_difference", {"shape1": "CylA", "shape2": "CylA", "result_name": "Self"}),
    ],
)
def test_booleans_of_an_object_with_itself_are_refused(mcp, gui_log, tool, args):
    if mcp.call("get_object", doc_name="LiveSelf", obj_name="CylA").is_error:
        assert_ok(mcp.call("create_document", name="LiveSelf"))
        assert_ok(mcp.call("create_object", doc_name="LiveSelf", obj_type="Part::Cylinder",
                           obj_name="CylA"))
        gui_log.reset()

    _rejected(mcp.call(tool, doc_name="LiveSelf", **args), "must be different objects")
    assert_clean(gui_log)
