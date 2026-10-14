"""Deferred body recomputes must be explained in caller-visible text."""

from types import SimpleNamespace as NS

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import execute_code_gui_task as task
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_response import finalize_gui_execute_response
from freecad_mcp.responses.execute_result import from_execute_result

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("call_recompute", [False, True], ids=["happy_print", "defect_deferred"])
def test_target_recompute_feedback_reaches_tool_text(monkeypatch, call_recompute):
    class Doc:
        def recompute(self):
            return 0  # The native commit fence defers this body call.

    doc = Doc()
    app = NS(ActiveDocument=None, listDocuments=lambda: {}, getDocument=lambda _: doc,
             Console=NS(PrintMessage=lambda _: None, PrintError=lambda _: None))
    monkeypatch.setattr(task, "build_execute_session", lambda **_: {})
    sink = {}
    options = {"document": "R22Feat", "recompute": "target"}
    code = "print('inspection')"
    if call_recompute:
        code = "doc = FreeCAD.getDocument('R22Feat')\nr = doc.recompute()\nprint('recompute-return', r)"
    provisional = task.run_execute_code_gui_task(
        code, options, freecad=app, collect_invalid_objects_fn=lambda: [],
        native_boundary=True, postcondition_sink=sink, manage_active_document=False,
    )
    assert provisional["ok"]
    rpc = finalize_gui_execute_response(lambda value: value, sink["finalize"](), options)
    result = from_execute_result(rpc, success_prefix="Executed", fail_prefix="Failed", capture_view=False)
    text = '\n'.join(item.text for item in result.content if item.type == 'text')
    assert not result.isError
    if call_recompute:
        assert 'recompute-return 0' in text
        assert 'deferred' in text.lower()
        assert 'target recompute' in text.lower()
    else:
        assert 'inspection' in text
        assert 'deferred' not in text.lower()


def test_none_recompute_feedback_requests_explicit_recompute(monkeypatch):
    class Doc:
        def recompute(self):
            return 0

    app = NS(ActiveDocument=None, listDocuments=lambda: {}, getDocument=lambda _: Doc(),
             Console=NS(PrintMessage=lambda _: None, PrintError=lambda _: None))
    monkeypatch.setattr(task, "build_execute_session", lambda **_: {})
    result = task.run_execute_code_gui_task(
        "FreeCAD.getDocument('Model').recompute()", {"document": "Model", "recompute": "none"},
        freecad=app, collect_invalid_objects_fn=lambda: [], native_boundary=True,
        manage_active_document=False,
    )
    rpc = finalize_gui_execute_response(lambda value: value, result, {"document": "Model"})
    tool = from_execute_result(rpc, success_prefix="Executed", fail_prefix="Failed", capture_view=False)
    text = '\n'.join(item.text for item in tool.content if item.type == 'text')
    assert 'recompute_document' in text
