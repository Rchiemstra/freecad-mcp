"""Round 21: distinguish actor selection from the native GUI selection."""

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


def _native(mcp, doc, code):
    # execute_code runs on the document owner; native selection requires Qt's
    # main thread even when execution_mode is "gui".
    import textwrap
    dispatched = "import FreeCADGui as Gui\nfrom PySide import QtCore, QtWidgets\n" + (
        "class NativeSelectionCall(QtCore.QObject):\n"
        "    @QtCore.Slot()\n"
        "    def run(self):\n"
        "        try:\n" + textwrap.indent(code, "            ") + "\n"
        "        except Exception as exc:\n"
        "            self.result = repr(exc)\n"
        "native_call = NativeSelectionCall()\n"
        "native_call.moveToThread(QtWidgets.QApplication.instance().thread())\n"
        "QtCore.QMetaObject.invokeMethod(native_call, 'run', QtCore.Qt.BlockingQueuedConnection)\n"
        "print('R21Native=' + repr(native_call.result))\n"
        "native_call.deleteLater()\n"
    )
    return assert_ok(mcp.call("execute_code", document=doc, recompute="none",
                              execution_mode="gui", code=dispatched))


@pytest.mark.parametrize("require_scope", [False, True], ids=["happy_isolation", "defect_scope"])
def test_round21_personal_selection(mcp, gui_log, require_scope):
    doc = "R21SelectionScope"
    assert_ok(mcp.call("create_document", name=doc))
    try:
        assert_ok(mcp.call("create_object", doc_name=doc, obj_type="Part::Box", obj_name="Box"))
        native = _native(mcp, doc,
                         "Gui.Selection.clearSelection()\n"
                         f"Gui.Selection.addSelection('{doc}', 'Box', 'Face2')\n"
                         "self.result = 'ready'")
        assert "R21Native='ready'" in native.text, native.text
        selected = _payload(assert_ok(mcp.call(
            "select_subshapes", doc_name=doc, selections=["Box:Face1"], clear=True,
        )))
        native = _native(mcp, doc,
                         "self.result = [(s.ObjectName, list(s.SubElementNames)) "
                         "for s in Gui.Selection.getSelectionEx()]\n"
                         "Gui.Selection.clearSelection()")
        assert "R21Native=[('Box', ['Face2'])]" in native.text, native.text
        selection = _payload(assert_ok(mcp.call("get_selection")))
        state = _payload(assert_ok(mcp.call("get_gui_state")))
        expected = [{"document": doc, "object": "Box", "sub": "Face1"}]
        assert selection["selection"] == state["selection"] == expected
        if require_scope:
            for result in (selected, selection, state):
                assert result["selection_scope"] == "actor_personal"
                assert result["native_selection_included"] is False
    finally:
        assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)
