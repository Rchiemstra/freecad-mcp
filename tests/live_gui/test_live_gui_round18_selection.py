"""Round 18: selection in an owner callback must fail without losing the GUI."""

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


def test_round18_draft_inline_selection_keeps_process_alive(mcp, gui_log):
    assert_ok(mcp.call("create_document", name="R18_Draft"))
    # Verbatim Finding 1 call: recompute and select in the creation callback,
    # rather than selecting in a later queued GUI presentation callback.
    result = mcp.call(
        "execute_code", document="R18_Draft", recompute="none",
        execution_mode="gui", activate_document=True,
        code="import Draft\n"
             "import FreeCAD as App\n"
             "import FreeCADGui as Gui\n"
             "doc = App.getDocument('R18_Draft')\n"
             "rect = Draft.make_rectangle(20, 10)\n"
             "rect.Label = 'DraftRect'\n"
             "doc.recompute()\n"
             "Gui.Selection.clearSelection()\n"
             "Gui.Selection.addSelection(doc.Name, rect.Name)\n"
             "print('created', rect.Name, 'selected', bool(Gui.Selection.getSelection()))",
    )
    assert result.is_error, result.text
    assert "main thread" in result.text, result.text
    assert "FreeCADGui.Selection." in result.text, result.text
    # A Python error must roll back creation, keep the document, and leave the
    # process usable (the original failure returned RemoteDisconnected).
    assert_ok(mcp.call("get_runtime_info"))
    objects = assert_ok(mcp.call("get_objects", doc_name="R18_Draft"))
    assert "Rectangle" not in objects.text, objects.text
    undo = mcp.call("undo", doc_name="R18_Draft")
    assert undo.is_error, undo.text
    assert _payload(undo)["error_code"] == "EMPTY_HISTORY_STACK", undo.text
    assert_ok(mcp.call("close_document", doc_name="R18_Draft"))
    assert_clean(gui_log)
