import io
from types import SimpleNamespace as NS
import pytest
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_exec import run_python_on_gui_thread

pytestmark = pytest.mark.unit


def test_python_execution_still_captures_stdout():
    out = io.StringIO()
    app = NS(Console=NS(PrintMessage=lambda x: None, PrintError=lambda x: None))
    assert run_python_on_gui_thread('print(42)', out, freecad=app) == (True, None)
    assert out.getvalue() == '42\n'


def test_deferred_recompute_is_observed_once():
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_exec import observe_recompute_calls
    class Doc:
        def recompute(self):
            pass
    with observe_recompute_calls() as calls:
        doc = Doc()
        doc.recompute()
        doc.recompute()
    assert calls == ['recompute']
