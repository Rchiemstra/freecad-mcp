"""Live undo readiness diagnostics from round 16."""

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


def test_ready_document_undo_succeeds(mcp, gui_log):
    doc = "R16ReadyUndo"
    assert_ok(mcp.call("create_document", name=doc))
    assert_ok(mcp.call("create_object", doc_name=doc, obj_type="Part::Box", obj_name="Box"))
    assert_ok(mcp.call("undo", doc_name=doc))
    empty = mcp.call("undo", doc_name=doc)
    assert empty.is_error
    assert _payload(empty)["error_code"] == "EMPTY_HISTORY_STACK", empty.text
    assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)


def test_pending_recompute_undo_explains_live_state_and_recovery(mcp, gui_log):
    doc = "R16PendingUndo"
    assert_ok(mcp.call("create_document", name=doc))
    try:
        assert_ok(mcp.call("execute_code", document=doc, recompute="none",
                           execution_mode="gui",
                           code="import FreeCAD\nFreeCAD.getDocument(%r).addObject('Part::Box','Box')" % doc))
        rejected = mcp.call("undo", doc_name=doc)
        assert rejected.is_error, rejected.text
        payload = _payload(rejected)
        assert payload["error_code"] == "MUTATION_NOT_READY", rejected.text
        live = payload["diagnostics"]["documents"][0]
        assert live["must_execute"] is True
        assert live["recomputing"] is False
        assert live["undo_count"] == 1
        assert "pending recompute work" in rejected.text
        assert "Live undo count: 1" in rejected.text
        assert "recompute_document" in rejected.text
        assert_ok(mcp.call("recompute_document", doc_name=doc))
        assert_ok(mcp.call("undo", doc_name=doc))
    finally:
        assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)
