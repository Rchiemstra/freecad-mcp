"""A real edit after grouped undo retires redo at both ends of a Label rename."""
import time

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round27 import _history
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


@pytest.mark.parametrize("history_path", ["mcp", "native_gui"])
@pytest.mark.parametrize("branch_doc", ["ReviewSrc", "ReviewDep"])
def test_grouped_redo_after_real_branch(mcp, live_gui, gui_log, history_path, branch_doc):
    opened = []
    request = live_gui.workdir / "review_native_history.txt"
    try:
        for doc in ("ReviewSrc", "ReviewDep"):
            assert_ok(mcp.call("create_document", name=doc))
            opened.append(doc)
            assert_ok(mcp.call("create_object", doc_name=doc, obj_name="Box", obj_type="Part::Box"))
            assert_ok(mcp.call("save_document_as", selector={"document_name": doc},
                               destination=str(live_gui.workdir / (doc + ".FCStd")), overwrite=True))
        assert_ok(mcp.call("set_expression", doc_name="ReviewDep", object_name="Box",
                           prop_path="Length", expression="ReviewSrc#<<Box>>.Width"))
        if history_path == "native_gui":
            request.write_text("")
            assert_ok(mcp.call("execute_code", document="ReviewDep", recompute="none",
                               execution_mode="gui", code=f'''import FreeCAD, FreeCADGui as Gui
from pathlib import Path
from draftutils.gui_utils import run_gui_setup
def install_review_driver():
    from PySide import QtCore
    timer = QtCore.QTimer(Gui.getMainWindow())
    request = Path({str(request)!r})
    def poll():
        action = request.read_text()
        if not action:
            return
        request.write_text('')
        if action == 'stop':
            timer.stop()
            timer.deleteLater()
            return
        Gui.setActiveDocument('ReviewDep')
        Gui.activateView('Gui::View3DInventor', True)
        Gui.runCommand('Std_' + action.title(), 0)
    timer.timeout.connect(poll)
    timer.start(50)
run_gui_setup(FreeCAD.getDocument('ReviewDep').getObject('Box'), install_review_driver)
'''))
        assert_ok(mcp.call("edit_object", doc_name="ReviewSrc", obj_name="Box",
                           obj_properties={"Label": "RenamedBox"}))
        assert_ok(mcp.call("undo", doc_name="ReviewSrc"))
        assert_ok(mcp.call("edit_object", doc_name=branch_doc, obj_name="Box",
                           obj_properties={"Height": 17}))
        if history_path == "mcp":
            result = mcp.call("redo", doc_name="ReviewDep")
            # An empty redo can report either no-op success or an explicit refusal.
            if not result.ok:
                assert "redo" in result.text.lower(), result.text
        else:
            request.write_text("redo")
            deadline = time.monotonic() + 10
            while request.read_text() and time.monotonic() < deadline:
                time.sleep(0.05)
            assert request.read_text() == ""
            time.sleep(1)
        for doc in opened:
            assert _history(mcp, doc)["redo_count"] == 0
        expr = _payload(assert_ok(mcp.call("list_expressions", doc_name="ReviewDep", object_name="Box")))
        assert "<<Box>>.Width" in str(expr), expr
        assert "RenamedBox" not in str(expr), expr
        assert_ok(mcp.call("execute_code", document="ReviewSrc", recompute="none", execution_mode="gui",
                           code="import FreeCAD\nassert FreeCAD.getDocument('ReviewSrc').Box.Label == 'Box'"))
    finally:
        if history_path == "native_gui":
            request.write_text("stop")
            time.sleep(0.1)
        for doc in reversed(opened):
            assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)
