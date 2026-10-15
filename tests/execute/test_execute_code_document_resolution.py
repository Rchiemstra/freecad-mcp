"""An implicitly resolved active document must be visible in execution results."""
from types import SimpleNamespace
import pytest
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code import _prepare_native_gui_execution
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_response import finalize_gui_execute_response

pytestmark = pytest.mark.unit

def test_no_open_document_keeps_qt_execution_available():
    collaborators = SimpleNamespace(freecad=SimpleNamespace(ActiveDocument=None))
    options, document, recompute, failure = _prepare_native_gui_execution({}, collaborators)
    assert document is None
    assert recompute is False
    assert failure is None
    result = finalize_gui_execute_response(lambda x: x, {"ok": True, "stdout": "Qt available", "session": {}}, options)
    assert result["success"] is True
    assert "Qt available" in result["message"]

def test_active_document_fallback_reports_owner_venue_and_inference():
    collaborators = SimpleNamespace(freecad=SimpleNamespace(ActiveDocument=SimpleNamespace(Name="Model")))
    options, document, _, failure = _prepare_native_gui_execution({}, collaborators)
    assert document == "Model"
    assert failure is None
    result = finalize_gui_execute_response(lambda x: x,
        {"ok": False, "error": "GUI API 'FreeCADGui.getMainWindow' may only be used from the main thread", "traceback": None}, options)
    assert result["execution"] == {"mode": "gui", "venue": "document_owner_thread", "document": "Model", "document_source": "active"}
    assert "omitted document" in result["error"]
