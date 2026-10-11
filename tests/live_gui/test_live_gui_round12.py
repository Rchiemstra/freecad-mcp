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



def test_report_view_returns_newest_lines(mcp, gui_log):
    assert_ok(mcp.call("get_report_view", clear=True))
    assert_ok(mcp.call("execute_code", execution_mode="gui", recompute="none",
                       code="import FreeCAD as App\nApp.Console.PrintMessage('r12-old\\nr12-middle\\nr12-new\\n')"))
    result = _payload(assert_ok(mcp.call("get_report_view", max_lines=2)))
    assert "r12-new" in result["text"]
    assert "r12-old" not in result["text"]
    assert_clean(gui_log)



def test_plain_offset_geometry_survives_repeated_recomputes(mcp, gui_log):
    assert_ok(mcp.call('create_document', name='R12Offset'))
    assert_ok(mcp.call('sketch_create', doc_name='R12Offset', sketch_name='Sk'))
    for args in [dict(x1=0,y1=0,x2=10,y2=0),dict(x1=10,y1=0,x2=10,y2=10)]:
        assert_ok(mcp.call('sketch_add_line', doc_name='R12Offset', sketch_name='Sk', **args))
    assert_ok(mcp.call('sketch_offset', doc_name='R12Offset', sketch_name='Sk', geo_indices=[0,1], offset=1.5, copy=True))
    for _ in range(2):
        assert_ok(mcp.call('recompute_document', doc_name='R12Offset'))
    result = _payload(assert_ok(mcp.call('get_sketch_geometry', doc_name='R12Offset', sketch_name='Sk')))
    assert result['geometry_count'] == 4
    assert_ok(mcp.call('close_document', doc_name='R12Offset'))
    # scripts/reproduce_round12_offset.py produces the same warning without MCP.
    assert_clean(gui_log, 'Cannot find SKF modified Edge')



@pytest.mark.parametrize('variant', ['none', 'target', 'no_document', 'import_open'])
def test_execute_code_document_lifecycle_survives(mcp, gui_log, variant):
    assert_ok(mcp.call('create_document', name='R12Lifecycle'))
    kwargs = {'execution_mode': 'gui', 'recompute': 'target' if variant == 'target' else 'none'}
    if variant != 'no_document':
        kwargs['document'] = 'R12Lifecycle'
    code = "import FreeCAD as App\nApp.newDocument('R12Created')"
    if variant == 'import_open':
        code = ("import FreeCAD as App, types, sys\n"
                "mod = types.ModuleType('R12LifecycleImport')\n"
                "mod.open = lambda filename: App.newDocument('R12Created')\n"
                "sys.modules[mod.__name__] = mod\nmod.open('/tmp/qa.r12')")
    result = mcp.call('execute_code', code=code, **kwargs)
    if not result.ok:
        assert 'lifecycle' in result.text.lower() and 'unavailable' in result.text.lower()
        assert 'create_document' in result.text and 'open_document' in result.text
    docs = _payload(assert_ok(mcp.call('list_documents')))
    # A successful variant may create a document; always verify the next tool answers.
    for name in ['R12Created', 'R12Lifecycle']:
        if name in str(docs):
            assert_ok(mcp.call('close_document', doc_name=name))
    assert_clean(gui_log, 'lifecycle', 'unavailable', 'newDocument', 'Error executing Python', 'postflight')



def test_modal_dialog_is_reported_without_dispatching_gui_work(mcp, gui_log):
    # With no open document this body runs on the Qt main thread.
    docs = assert_ok(mcp.call('list_documents'))
    assert 'R12' not in docs.text
    assert_ok(mcp.call('execute_code', execution_mode='gui', recompute='none',
                       code="from PySide import QtCore, QtWidgets\n"
                            "r12_dialog = QtWidgets.QMessageBox()\n"
                            "r12_dialog.setWindowTitle('Round 12 modal')\n"
                            "r12_dialog.setText('Test dialog')\n"
                            "r12_dialog.setModal(True)\nr12_dialog.show()\n"
                            "QtCore.QTimer.singleShot(8000, r12_dialog.close)"))
    try:
        failed = mcp.call('get_report_view')
        assert not failed.ok
        assert 'GUI_BLOCKED_BY_MODAL_DIALOG' in failed.text
        assert 'Round 12 modal' in failed.text
        state = _payload(assert_ok(mcp.call('get_gui_state')))
        assert state['modal_dialog'] == 'Round 12 modal'
        runtime = _payload(assert_ok(mcp.call('get_runtime_info')))
        assert runtime['gui']['modal_dialog'] == 'Round 12 modal'
    finally:
        import time
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            state = _payload(assert_ok(mcp.call('get_runtime_info')))
            if not state.get('gui', {}).get('modal_dialog'):
                break
            time.sleep(.1)
    assert_ok(mcp.call('get_report_view'))
    assert_clean(gui_log)



def test_registered_import_module_opens_on_gui_thread(mcp, gui_log, live_gui):
    path = live_gui.workdir / 'import.r12import'
    path.write_text('tiny import')
    assert_ok(mcp.call('execute_code', execution_mode='gui', recompute='none',
                       code="import FreeCAD as App, types, sys\n"
                            "from PySide import QtCore, QtWidgets\n"
                            "mod = types.ModuleType('R12Importer')\n"
                            "def r12_open(filename):\n"
                            "    assert QtCore.QThread.currentThread() == QtWidgets.QApplication.instance().thread()\n"
                            "    App.newDocument('R12Imported')\n"
                            "mod.open = r12_open\nsys.modules[mod.__name__] = mod\n"
                            "App.addImportType('Round 12 (*.r12import)', mod.__name__)"))
    opened = _payload(assert_ok(mcp.call('open_document', path=str(path))))
    assert opened['document_name'] == 'R12Imported'
    assert_ok(mcp.call('close_document', doc_name='R12Imported'))
    assert_clean(gui_log)



def test_touched_feature_is_not_a_recompute_error(mcp, gui_log):
    assert_ok(mcp.call('create_document', name='R12Touched'))
    result = mcp.call('execute_code', document='R12Touched', execution_mode='gui', recompute='none',
                      code="import FreeCAD as App, Part\n"
                           "doc = App.getDocument('R12Touched')\n"
                           "obj = doc.addObject('Part::Feature','Feature')\n"
                           "obj.Shape = Part.makeBox(10,10,10)\ndoc.recompute()")
    assert_ok(result)
    assert '"recompute_errors": []' in result.text or not result.payload.get('recompute_errors')
    assert 'deferred' in result.payload['note'].lower()
    assert_ok(mcp.call('recompute_document', doc_name='R12Touched'))
    assert_ok(mcp.call('close_document', doc_name='R12Touched'))
    assert_clean(gui_log)



def test_dropped_read_only_transport_retries_against_live_freecad(mcp, live_gui, gui_log, monkeypatch):
    import uuid
    from http.client import RemoteDisconnected
    from freecad_mcp.freecad_client import FreeCADConnection
    from freecad_mcp._shared.protocol.manifest import load_instance_manifest, make_mcp_runtime_identity
    from freecad_mcp._shared.protocol.profile_secret import load_profile_secret
    from freecad_mcp._shared.protocol.handshake_request import build_handshake_request_from_manifest
    from freecad_mcp._shared.protocol.handshake_response import verify_handshake_response_from_manifest
    from freecad_mcp.generated.capabilities.connection_methods.connection_invoke_v2_helpers import invoke_v2_transport
    from freecad_mcp.rpc_session import RpcAuthenticationContext
    from freecad_mcp.build_info import build_id
    manifest = load_instance_manifest(live_gui.manifest)
    identity = make_mcp_runtime_identity(client_build_id=build_id)
    secret = load_profile_secret(manifest.auth_secret_file)
    conn = FreeCADConnection(host=manifest.rpc_host, port=manifest.rpc_port)
    request = build_handshake_request_from_manifest(secret=secret, mcp=identity, manifest=manifest)
    raw = conn.invoke_rpc('handshake_v2', request, control=True)
    verified = verify_handshake_response_from_manifest(raw, secret=secret,
                expected_client_nonce=request['client_nonce'], manifest=manifest)
    assert_ok(mcp.call('create_document', name='R12Retry'))
    original = conn.invoke_rpc
    calls = []
    def dropped_once(*args, **kwargs):
        calls.append(args[0])
        if len(calls) == 1:
            raise RemoteDisconnected('injected response drop')
        return original(*args, **kwargs)
    monkeypatch.setattr(conn, 'invoke_rpc', dropped_once)
    try:
        for method, params in [('get_objects', {'doc_name':'R12Retry'}),
                               ('execute_code', {'code':'print(42)', 'options':{
                                   'document':'R12Retry','read_only':True,'execution_mode':'worker','timeout_seconds':15}})]:
            calls.clear()
            context = RpcAuthenticationContext(request_id=str(uuid.uuid4()), session_token=verified.session_token,
                                                mcp_runtime_id=identity.runtime_id)
            result = invoke_v2_transport(conn, method, params, context, control=False, timeout=30)
            assert result.get('success') is not False, result
            assert len(calls) == 2
    finally:
        conn.server.close()
        conn.control_server.close()
        assert_ok(mcp.call('close_document', doc_name='R12Retry'))
    assert_clean(gui_log)

