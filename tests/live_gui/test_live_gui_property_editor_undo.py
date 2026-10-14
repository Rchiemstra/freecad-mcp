"""Resetting editors for a deleted selection must not commit during undo."""

import time

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui
WARNING = "Cannot commit transaction while transacting"


@pytest.mark.parametrize("selected", [False, True], ids=["unselected", "selected"])
def test_draft_undo_does_not_commit_editor_transaction(mcp, gui_log, selected):
    doc = "DraftUndoSelected" if selected else "DraftUndoUnselected"
    assert_ok(mcp.call("create_document", name=doc))
    try:
        assert_ok(mcp.call("execute_code", document=doc, recompute="target", execution_mode="gui",
                           code="import Draft\nr = Draft.make_rectangle(20, 10)"))
        # Draft selects the new rectangle in its queued presentation. Explicitly
        # establish the test selection and let both property models populate.
        time.sleep(0.5)
        assert_ok(mcp.call("execute_code", document=doc, execution_mode="gui", recompute="none",
                           code="import FreeCADGui as Gui\nfrom draftutils import gui_utils\n"
                                "def select_rectangle():\n    Gui.Selection.clearSelection()\n" +
                                ("    Gui.Selection.addSelection(r)\n" if selected else "") +
                                "gui_utils.run_gui_setup(r, select_rectangle)"))
        time.sleep(0.5)
        gui_log.reset()
        assert_ok(mcp.call("undo", doc_name=doc))
        time.sleep(0.2)
        empty = mcp.call("undo", doc_name=doc)
        assert empty.is_error
        assert _payload(empty)["error_code"] == "EMPTY_HISTORY_STACK", empty.text
        warnings = [line for line in gui_log.problems() if WARNING in line]
        assert len(warnings) == 0, f"{WARNING}: {len(warnings)} occurrences\n" + "\n".join(warnings)
    finally:
        assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)
