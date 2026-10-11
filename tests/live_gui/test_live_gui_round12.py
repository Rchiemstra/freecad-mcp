"""Regression coverage for live GUI stress round 12 and import addon feedback."""
from __future__ import annotations

import pytest
from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


def test_property_projection_omits_missing_properties_and_aliases(mcp, gui_log):
    assert_ok(mcp.call("create_document", name="R12Properties"))
    assert_ok(mcp.call("body_create", doc_name="R12Properties", body_name="Body"))
    assert_ok(mcp.call("spreadsheet_create", doc_name="R12Properties", sheet_name="Sheet"))
    assert_ok(mcp.call("spreadsheet_set_cells", doc_name="R12Properties", sheet_name="Sheet",
                       cells=[{"address": "A1", "alias": "Width", "value": "40 mm"}]))
    rows = _payload(assert_ok(mcp.call("get_objects", doc_name="R12Properties",
                                      include_properties=["Type", "Width", "Length"])))
    for row in rows["objects"]:
        if row["Name"] in {"Body", "Sheet"}:
            assert row["Properties"] == {}
    assert_ok(mcp.call("close_document", doc_name="R12Properties"))
    assert_clean(gui_log)



def test_part_and_body_origins_have_owners(mcp, gui_log):
    assert_ok(mcp.call("create_document", name="R12Tree"))
    assert_ok(mcp.call("create_part_container", doc_name="R12Tree", part_name="Part"))
    assert_ok(mcp.call("body_create", doc_name="R12Tree", body_name="Body"))
    tree = _payload(assert_ok(mcp.call("get_document_tree", doc_name="R12Tree", max_depth=3)))
    assert {row["Name"] for row in tree["roots"]} == {"Part", "Body"}
    for row in tree["roots"]:
        origin = next(child for child in row["children"] if child["TypeId"] == "App::Origin")
        assert len(origin["children"]) >= 6
    assert_ok(mcp.call("close_document", doc_name="R12Tree"))
    assert_clean(gui_log)



def test_slot_rejects_zero_width_and_constrains_joins(mcp, gui_log):
    assert_ok(mcp.call("create_document", name="R12Slot"))
    assert_ok(mcp.call("sketch_create", doc_name="R12Slot", sketch_name="Sk"))
    failed = mcp.call("sketch_add_slot", doc_name="R12Slot", sketch_name="Sk",
                      x1=0, y1=0, x2=20, y2=0, width=0)
    assert not failed.ok
    assert "width must be greater than zero" in failed.text
    assert_ok(mcp.call("sketch_add_slot", doc_name="R12Slot", sketch_name="Sk",
                       x1=0, y1=0, x2=20, y2=0, width=6))
    geo = _payload(assert_ok(mcp.call("get_sketch_geometry", doc_name="R12Slot",
                                     sketch_name="Sk", include_constraints=True)))
    types = [c["type"] for c in geo["constraints"]]
    assert types.count("Tangent") == 4
    assert_ok(mcp.call("close_document", doc_name="R12Slot"))
    assert_clean(gui_log)



def test_trim_without_an_intersection_is_clear(mcp, gui_log):
    assert_ok(mcp.call("create_document", name="R12Trim"))
    assert_ok(mcp.call("sketch_create", doc_name="R12Trim", sketch_name="Sk"))
    assert_ok(mcp.call("sketch_add_line", doc_name="R12Trim", sketch_name="Sk",
                       x1=0, y1=0, x2=20, y2=0))
    # The original failure used the collapsed zero-width slot. FreeCAD's
    # normal trim of an isolated curve deletes it successfully.
    assert_ok(mcp.call("execute_code", document="R12Trim", recompute="none",
                       code="import FreeCAD as App, Part\n"
                            "sk = App.getDocument('R12Trim').getObject('Sk')\n"
                            "sk.addGeometry(Part.LineSegment(App.Vector(20,0,0), App.Vector(0,0,0)), False)\n"
                            "sk.addGeometry(Part.ArcOfCircle(Part.Circle(App.Vector(0,0,0), App.Vector(0,0,1),0),1.57079632679,4.71238898038),False)"))
    failed = mcp.call("sketch_trim", doc_name="R12Trim", sketch_name="Sk",
                      geo_index=0, point_x=5, point_y=5)
    assert not failed.ok
    assert "no intersection near the trim point" in failed.text
    assert_ok(mcp.call("close_document", doc_name="R12Trim"))
    assert_clean(gui_log, "Standard_NullValue", "Edge too small")



def test_unknown_object_type_is_clear(mcp, gui_log):
    assert_ok(mcp.call("create_document", name="R12Unknown"))
    failed = mcp.call("create_object", doc_name="R12Unknown", obj_name="Nope", obj_type="Not::AType")
    assert not failed.ok
    assert "Unknown object type: Not::AType" in failed.text
    assert_ok(mcp.call("get_objects", doc_name="R12Unknown"))
    assert_ok(mcp.call("close_document", doc_name="R12Unknown"))
    assert_clean(gui_log, "No module named 'Not'", "ModuleNotFoundError")



def test_area_expression_cannot_bind_length(mcp, gui_log):
    assert_ok(mcp.call("create_document", name="R12Units"))
    assert_ok(mcp.call("create_object", doc_name="R12Units", obj_type="Part::Box", obj_name="Box"))
    assert_ok(mcp.call("set_expression", doc_name="R12Units", object_name="Box",
                       prop_path="Width", expression="40 mm"))
    failed = mcp.call("set_expression", doc_name="R12Units", object_name="Box",
                      prop_path="Width", expression="40 mm * 30 mm")
    assert not failed.ok
    assert "EXPRESSION_UNIT_MISMATCH" in failed.text or "Unit mismatch" in failed.text
    listed = _payload(assert_ok(mcp.call("list_expressions", doc_name="R12Units", object_name="Box")))
    assert "40 mm" in str(listed)
    assert "30 mm" not in str(listed)
    assert_ok(mcp.call("close_document", doc_name="R12Units"))
    assert_clean(gui_log)

