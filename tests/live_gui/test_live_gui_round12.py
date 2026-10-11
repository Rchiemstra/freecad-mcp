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



def test_partdesign_base_scope_error_explains_body(mcp, gui_log):
    assert_ok(mcp.call("create_document", name="R12Scope"))
    assert_ok(mcp.call("create_object", doc_name="R12Scope", obj_type="Part::Box", obj_name="Base"))
    failed = mcp.call("create_object", doc_name="R12Scope", obj_type="PartDesign::Thickness",
                      obj_name="Thickness", obj_properties={"Base": "Base"})
    assert not failed.ok
    assert "links are out of scope" in failed.text
    assert "inside the body" in failed.text
    assert_ok(mcp.call("close_document", doc_name="R12Scope"))
    assert_clean(gui_log, "out of scope", "No Base object linked")



def test_shape_coordinates_apply_placement_once(mcp, gui_log):
    assert_ok(mcp.call("create_document", name="R12Placement"))
    assert_ok(mcp.call("create_part_container", doc_name="R12Placement", part_name="Part"))
    assert_ok(mcp.call("create_object", doc_name="R12Placement", obj_type="Part::Box", obj_name="Box",
                       obj_properties={"Length": 10, "Width": 10, "Height": 10,
                                       "Placement": {"Base": {"x": 20, "y": 0, "z": 0}}}))
    assert_ok(mcp.call("move_object", doc_name="R12Placement", obj_name="Box", target_container="Part"))
    faces = _payload(assert_ok(mcp.call("find_faces", doc_name="R12Placement", object_name="Box",
                                       normal_approx={"x": 0, "y": 0, "z": 1})))
    assert faces["results"][0]["global_center"]["x"] == pytest.approx(25)
    assert_ok(mcp.call("close_document", doc_name="R12Placement"))
    assert_clean(gui_log)



def test_rotated_shape_and_relative_binder_use_each_frame_once(mcp, gui_log):
    import math
    assert_ok(mcp.call('create_document', name='R12Frames'))
    assert_ok(mcp.call('create_part_container', doc_name='R12Frames', part_name='Part'))
    assert_ok(mcp.call('edit_object', doc_name='R12Frames', obj_name='Part', obj_properties={
        'Placement': {'Base':{'x':100,'y':0,'z':0}, 'Rotation':{'Axis':{'x':0,'y':1,'z':0},'Angle':30}}}))
    assert_ok(mcp.call('create_object', doc_name='R12Frames', obj_name='Box', obj_type='Part::Box', obj_properties={
        'Length':10,'Width':10,'Height':10,
        'Placement':{'Base':{'x':20,'y':0,'z':0},'Rotation':{'Axis':{'x':0,'y':1,'z':0},'Angle':15}}}))
    assert_ok(mcp.call('move_object', doc_name='R12Frames', obj_name='Box', target_container='Part'))
    root = math.sqrt(.5)
    faces = _payload(assert_ok(mcp.call('find_faces', doc_name='R12Frames', object_name='Box',
                                       normal_approx={'x':root,'y':0,'z':root})))
    top = faces['results'][0]
    assert top['global_normal'] == pytest.approx({'x':root,'y':0,'z':root}, abs=1e-5)
    assert top['global_center']['x'] == pytest.approx(100 + 20 * math.cos(math.pi/6) + 15 * root, abs=1e-5)
    normal = _payload(assert_ok(mcp.call('face_normal', doc_name='R12Frames', object_name='Box', face=top['sub'])))
    assert normal['global_normal'] == pytest.approx(top['global_normal'])
    assert_ok(mcp.call('body_create', doc_name='R12Frames', body_name='Body'))
    assert_ok(mcp.call('create_subshape_binder', doc_name='R12Frames', binder_name='Binder',
                       source_object='Box', target_body='Body', relative=True))
    source = _payload(assert_ok(mcp.call('inspect_geometry', doc_name='R12Frames', object_name='Box')))
    binder = _payload(assert_ok(mcp.call('inspect_geometry', doc_name='R12Frames', object_name='Binder')))
    assert binder['global_bbox'] == pytest.approx(source['global_bbox'])
    assert_ok(mcp.call('close_document', doc_name='R12Frames'))
    assert_clean(gui_log)



def test_cross_document_expression_binds_and_recomputes(mcp, gui_log, live_gui):
    for name in ['R12Src', 'R12Dst']:
        assert_ok(mcp.call('create_document', name=name))
        assert_ok(mcp.call('create_object', doc_name=name, obj_name='Box', obj_type='Part::Box',
                           obj_properties={'Length': 25 if name == 'R12Src' else 10}))
        assert_ok(mcp.call('save_document_as', selector={'document_name': name},
                           destination=str(live_gui.workdir / (name + '.FCStd')), overwrite=True))
    result = _payload(assert_ok(mcp.call('set_expression', doc_name='R12Dst', object_name='Box',
                                        prop_path='Length', expression='R12Src#Box.Length')))
    assert '25' in result['bound_value']
    assert_ok(mcp.call('close_document', doc_name='R12Dst'))
    assert_ok(mcp.call('close_document', doc_name='R12Src'))
    assert_clean(gui_log, 'unresolved cross-document dependency')



def test_worker_error_keeps_traceback_and_last_error(mcp, gui_log):
    assert_ok(mcp.call('create_document', name='R12Worker'))
    failed = mcp.call('execute_code', document='R12Worker', read_only=True, execution_mode='worker',
                      code="print('misleading stdout')\nraise RuntimeError('qa boom')", timeout_seconds=15)
    assert not failed.ok
    assert 'RuntimeError: qa boom' in failed.text
    assert 'Traceback' in failed.text or 'line 2' in failed.text
    status = _payload(assert_ok(mcp.call('get_worker_status')))
    assert 'qa boom' in status['last_error']
    assert_ok(mcp.call('execute_code', document='R12Worker', read_only=True, execution_mode='worker',
                       code='print(2)', timeout_seconds=15))
    assert _payload(assert_ok(mcp.call('get_worker_status')))['last_error'] is None
    assert_ok(mcp.call('close_document', doc_name='R12Worker'))
    assert_clean(gui_log, 'worker.*failed', 'qa boom')



def _red_box(mcp, document):
    assert_ok(mcp.call("create_document", name=document))
    assert_ok(mcp.call("create_object", doc_name=document, obj_name="Box", obj_type="Part::Box",
                       obj_properties={"Length": 10, "Width": 10, "Height": 10,
                                       "ViewObject": {"ShapeColor": [1, 0, 0, 1]}}))



def _box_view(mcp, document):
    rows = _payload(assert_ok(mcp.call("get_objects", doc_name=document, include_view=True)))
    return next(row["ViewObject"] for row in rows["objects"] if row["Name"] == "Box")



def test_red_box_creation(mcp, gui_log):
    _red_box(mcp, "R12RedHappy")
    assert _box_view(mcp, "R12RedHappy")["ShapeColor"][:3] == pytest.approx([1, 0, 0])
    assert_ok(mcp.call("close_document", doc_name="R12RedHappy"))
    assert_clean(gui_log)



def test_visibility_edits_preserve_color(mcp, gui_log):
    _red_box(mcp, "R12RedDefect")
    try:
        for visibility in [False, True]:
            assert_ok(mcp.call("edit_object", doc_name="R12RedDefect", obj_name="Box",
                               obj_properties={"ViewObject": {"Visibility": visibility}}))
            view = _box_view(mcp, "R12RedDefect")
            assert view["Visibility"] is visibility
            assert view["ShapeColor"][:3] == pytest.approx([1, 0, 0])
    finally:
        assert_ok(mcp.call("close_document", doc_name="R12RedDefect"))
    assert_clean(gui_log)

