"""Native expression tuples are bindings even without a Python getter."""
from types import SimpleNamespace
import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.diagnostics_io_actions import diagnose_parametric

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("getter", [True, False], ids=["happy_getter", "defect_native_tuple"])
def test_constraint_expression_diagnosis(getter):
    sketch = SimpleNamespace(Name="Sketch", TypeId="Sketcher::SketchObject", State=[],
                             ExpressionEngine=[(".Constraints.W", "SrcDoc#<<Dims>>.Wall")])
    if getter:
        sketch.getExpression = lambda path: "SrcDoc#<<Dims>>.Wall"
    document = SimpleNamespace(Name="DepDoc", Objects=[sketch])
    assert diagnose_parametric(document, None)["expression_issues"] == []
