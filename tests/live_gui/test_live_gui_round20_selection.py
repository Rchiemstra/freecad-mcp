"""Round 20: personal selections must not outlive their objects."""

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


def _selection(mcp, expected):
    selection = _payload(assert_ok(mcp.call("get_selection")))
    state = _payload(assert_ok(mcp.call("get_gui_state")))
    assert selection["selection"] == expected
    assert selection["count"] == len(expected)
    assert state["selection"] == expected
    assert state["selection_count"] == len(expected)


def test_round20_selection_select_and_clear(mcp, gui_log):
    doc = "R20SelectionHappy"
    assert_ok(mcp.call("create_document", name=doc))
    try:
        assert_ok(mcp.call("create_object", doc_name=doc, obj_type="Part::Box", obj_name="BoxA"))
        assert_ok(mcp.call("select_subshapes", doc_name=doc, selections=["BoxA.Face1"], clear=True))
        _selection(mcp, [{"document": doc, "object": "BoxA", "sub": "Face1"}])
        assert_ok(mcp.call("select_subshapes", doc_name=doc, selections=[], clear=True))
        _selection(mcp, [])
    finally:
        assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)


@pytest.mark.parametrize("recreate", [False, True])
def test_round20_selection_delete_history_and_recreate(mcp, gui_log, recreate):
    doc = f"R20SelectionDelete{int(recreate)}"
    assert_ok(mcp.call("create_document", name=doc))
    try:
        assert_ok(mcp.call("create_object", doc_name=doc, obj_type="Part::Box", obj_name="BoxA"))
        assert_ok(mcp.call("select_subshapes", doc_name=doc, selections=["BoxA"], clear=True))
        assert_ok(mcp.call("delete_object", doc_name=doc, obj_name="BoxA"))
        if recreate:
            # No selection read between delete and replacement: merely filtering
            # nonexistent names at read time would miss this case.
            assert_ok(mcp.call("create_object", doc_name=doc, obj_type="Part::Box", obj_name="BoxA"))
        _selection(mcp, [])
        assert_ok(mcp.call("undo", doc_name=doc))
        _selection(mcp, [])
        assert_ok(mcp.call("redo", doc_name=doc))
        _selection(mcp, [])
        native = assert_ok(mcp.call(
            "execute_code", document=doc, recompute="none", execution_mode="gui",
            code="import FreeCADGui as Gui\n"
                 "print('R20NativeSelection=' + repr([o.Name for o in Gui.Selection.getSelection()]))",
        ))
        assert "R20NativeSelection=[]" in native.text, native.text
    finally:
        assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)
