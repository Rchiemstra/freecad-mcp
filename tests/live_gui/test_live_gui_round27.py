"""Round 27: mixed Label histories and standalone origin isolation."""
import time

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


def _history(mcp, doc):
    return _payload(assert_ok(mcp.call("get_mutation_readiness", doc_name=doc)))["documents"][0]


def _pad(mcp, doc, body, sketch, pad, length):
    assert_ok(mcp.call("body_create", doc_name=doc, body_name=body))
    assert_ok(mcp.call("sketch_create", doc_name=doc, sketch_name=sketch,
                       body_name=body, attach_to="XY_Plane"))
    assert_ok(mcp.call("sketch_add_rectangle", doc_name=doc, sketch_name=sketch,
                       x1=0, y1=0, x2=40, y2=20))
    assert_ok(mcp.call("pad_feature", doc_name=doc, body_name=body, sketch_name=sketch,
                       pad_name=pad, length=length, strict=True))


@pytest.mark.parametrize("diagnostic", [False, True], ids=["direct", "diagnostic_between"])
@pytest.mark.parametrize("local", [False, True], ids=["external_only", "mixed_references"])
@pytest.mark.parametrize("history_path", ["mcp", "native_gui"])
def test_round27_saved_label_redo(mcp, live_gui, gui_log, local, history_path, diagnostic):
    opened = []
    native_request = live_gui.workdir / f"native_history_{local}.txt"
    try:
        assert_ok(mcp.call("create_document", name="R27_Src"))
        opened.append("R27_Src")
        assert_ok(mcp.call("spreadsheet_create", doc_name="R27_Src", sheet_name="Dims"))
        assert_ok(mcp.call("spreadsheet_set_cells", doc_name="R27_Src", sheet_name="Dims",
                           cells=[{"address": "A1", "value": 10, "alias": "PadLen"}]))
        _pad(mcp, "R27_Src", "Body", "Sketch", "Pad", 10)
        if local:
            assert_ok(mcp.call("set_expression", doc_name="R27_Src", object_name="Pad",
                               prop_path="Length", expression="<<Dims>>.PadLen"))
        assert_ok(mcp.call("save_document_as", selector={"document_name": "R27_Src"},
                           destination=str(live_gui.workdir / "r27_src.FCStd"), overwrite=True))
        assert_ok(mcp.call("create_document", name="R27_Dep"))
        opened.append("R27_Dep")
        assert_ok(mcp.call("body_create", doc_name="R27_Dep", body_name="DepBody"))
        assert_ok(mcp.call("spreadsheet_create", doc_name="R27_Dep", sheet_name="DepSheet"))
        assert_ok(mcp.call("spreadsheet_set_cells", doc_name="R27_Dep", sheet_name="DepSheet",
                           cells=[{"address": "A1", "value": 5, "alias": "LocalLen"}]))
        # The body is already present, matching the stress repro's order.
        assert_ok(mcp.call("sketch_create", doc_name="R27_Dep", sketch_name="DepSketch",
                           body_name="DepBody", attach_to="XY_Plane"))
        assert_ok(mcp.call("sketch_add_rectangle", doc_name="R27_Dep", sketch_name="DepSketch",
                           x1=0, y1=0, x2=20, y2=10))
        assert_ok(mcp.call("pad_feature", doc_name="R27_Dep", sketch_name="DepSketch",
                           pad_name="DepPad", length=5, body_name="DepBody", strict=True))
        assert_ok(mcp.call("save_document_as", selector={"document_name": "R27_Dep"},
                           destination=str(live_gui.workdir / "r27_dep.FCStd"), overwrite=True))
        assert_ok(mcp.call("set_expression", doc_name="R27_Dep", object_name="DepPad",
                           prop_path="Length", expression="R27_Src#<<Dims>>.PadLen"))
        assert_ok(mcp.call("spreadsheet_set_cells", doc_name="R27_Dep", sheet_name="DepSheet",
                           cells=[{"address": "A1", "value": "=R27_Src#<<Dims>>.PadLen"}]))
        if history_path == "native_gui":
            native_request.write_text("")
            # Issue native commands directly on the GUI thread, without
            # routing the history request through another compatibility commit.
            code = f"""import FreeCAD, FreeCADGui as Gui
from pathlib import Path
from draftutils.gui_utils import run_gui_setup
def install_history_driver():
    from PySide import QtCore
    timer = QtCore.QTimer(Gui.getMainWindow())
    request = Path({str(native_request)!r})
    def poll():
        action = request.read_text()
        if not action:
            return
        request.write_text('')
        if action == 'stop':
            timer.stop()
            timer.deleteLater()
            return
        Gui.setActiveDocument('R27_Src')
        Gui.activateView('Gui::View3DInventor', True)
        Gui.runCommand('Std_' + action.title(), 0)
    timer.timeout.connect(poll)
    timer.start(50)
run_gui_setup(FreeCAD.getDocument('R27_Src').getObject('Dims'), install_history_driver)
"""
            assert_ok(mcp.call("execute_code", document="R27_Src", recompute="none",
                               execution_mode="gui", code=code))
        before = {doc: _history(mcp, doc) for doc in opened}
        assert_ok(mcp.call("edit_object", doc_name="R27_Src", obj_name="Dims",
                           obj_properties={"Label": "DimsRenamed"}))
        for action, label, ud, rd in ((None, "DimsRenamed", 1, 0),
                                      ("undo", "Dims", 0, 1), ("redo", "DimsRenamed", 1, 0)):
            if action:
                if history_path == "mcp":
                    assert_ok(mcp.call(action, doc_name="R27_Src"))
                else:
                    native_request.write_text(action)
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline:
                        current = {doc: _history(mcp, doc) for doc in opened}
                        h = current["R27_Src"]
                        if (h["undo_count"] == before["R27_Src"]["undo_count"] + ud
                                and all(not item["collaboration_blocked"]
                                        and not item["pending_transaction"]
                                        and not item["recomputing"] for item in current.values())):
                            break
                        time.sleep(0.05)
                    else:
                        pytest.fail(f"Native GUI {action} did not move source history: {h}")
            time.sleep(1)  # Let GUI catch-up and delayed recomputes finish, as in stress.
            if action == "undo" and diagnostic:
                assert_ok(mcp.call("execute_code", document="R27_Dep", recompute="none",
                                   execution_mode="gui", code="import FreeCAD\ns = FreeCAD.getDocument('R27_Src'); d = FreeCAD.getDocument('R27_Dep')\nprint('SRC undo', s.UndoCount, 'redo', s.RedoCount)\nprint('DEP undo', d.UndoCount, 'redo', d.RedoCount)\nprint('DepPad expr', d.getObject('DepPad').ExpressionEngine)\nprint('DepSheet A1', d.getObject('DepSheet').getContents('A1'))"))
            for doc, obj in ([("R27_Src", "Pad")] if local and action == "redo" else []) + [("R27_Dep", "DepPad")]:
                expr = _payload(assert_ok(mcp.call("list_expressions", doc_name=doc, object_name=obj)))
                assert f"<<{label}>>.PadLen" in str(expr), expr
            if action == "redo":
                cells = _payload(assert_ok(mcp.call("spreadsheet_get_cells", doc_name="R27_Dep",
                                                   sheet_name="DepSheet", addresses=["A1"])))
                assert f"<<{label}>>.PadLen" in str(cells), cells
            for doc in opened:
                h = _history(mcp, doc)
                assert (h["undo_count"], h["redo_count"]) == (before[doc]["undo_count"] + ud,
                                                                          before[doc]["redo_count"] + rd), h
    finally:
        if history_path == "native_gui":
            native_request.write_text("stop")
            time.sleep(0.1)
        for doc in reversed(opened):
            assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)


@pytest.mark.parametrize("context", ["body", "root", "missing_root"])
def test_round27_standalone_plane(mcp, gui_log, context):
    doc = "ShapeMatrix"
    assert_ok(mcp.call("create_document", name=doc))
    try:
        assert_ok(mcp.call("create_part_container", doc_name=doc, part_name="OuterPart"))
        assert_ok(mcp.call("translate", doc_name=doc, obj_name="OuterPart", dx=100, dy=0, dz=20))
        args = {}
        if context == "body":
            assert_ok(mcp.call("body_create", doc_name=doc, body_name="Body"))
            args["body_name"] = "Body"
        elif context == "root":
            assert_ok(mcp.call("create_object", doc_name=doc, obj_name="RootOrigin", obj_type="App::Origin"))
        result = mcp.call("sketch_create", doc_name=doc, sketch_name="LooseSketch", attach_to="XY_Plane", **args)
        if context == "missing_root":
            assert not result.ok, result
            assert "unique document root origin" in result.text, result.text
        else:
            assert_ok(result)
            assert_ok(mcp.call("sketch_add_rectangle", doc_name=doc, sketch_name="LooseSketch",
                               x1=-10, y1=-5, x2=10, y2=5))
            assert_ok(mcp.call("translate", doc_name=doc, obj_name="OuterPart", dx=7, dy=0, dz=3))
            check = mcp.call("execute_code", document=doc, recompute="none", execution_mode="gui",
                             code="import FreeCAD\nd=FreeCAD.getDocument('ShapeMatrix')\ns=d.getObject('LooseSketch')\nassert s.Placement.Base.Length < 1e-8, str(s.Placement)\nassert abs(s.Shape.BoundBox.ZMin) < 1e-8\nassert abs(s.Shape.BoundBox.XMin + 10) < 1e-8")
            assert_ok(check)
    finally:
        assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)
