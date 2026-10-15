"""Round 13: distinguish omitted document from no resolved live document."""
import pytest
from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui

_CODE = "import FreeCADGui as Gui\nfrom PySide import QtWidgets\nmw = Gui.getMainWindow()\nprint('QT_AVAILABLE', mw is not None)\nprint(QtWidgets.QApplication.activeModalWidget())"

def test_execute_without_open_document_can_use_qt(mcp, gui_log):
    result = assert_ok(mcp.call("execute_code", execution_mode="gui", recompute="none", code=_CODE))
    assert "QT_AVAILABLE True" in result.text
    assert_clean(gui_log)

def test_execute_with_active_document_explains_inferred_owner_venue(mcp, gui_log):
    doc = "R13VenueActive"
    assert_ok(mcp.call("create_document", name=doc))
    try:
        result = mcp.call("execute_code", execution_mode="gui", recompute="none", code=_CODE)
        assert result.is_error is True
        payload = _payload(result)
        assert payload["execution"] == {"mode": "gui", "venue": "document_owner_thread", "document": doc, "document_source": "active"}
        assert "omitted document" in result.text
        assert "main thread" in result.text
        assert_ok(mcp.call("get_gui_state"))
    finally:
        assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log, "FreeCADGui.getMainWindow.*main thread")
