"""Native expression tuples are bindings even without a Python getter."""
from types import SimpleNamespace
import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.diagnostics_io_actions import diagnose_parametric
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.diagnostics import diagnose_parametric_gui

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("entrypoint", ["typed", "legacy"])
@pytest.mark.parametrize("getter", [True, False], ids=["happy_getter", "defect_native_tuple"])
def test_constraint_expression_diagnosis(getter, entrypoint):
    sketch = SimpleNamespace(Name="Sketch", TypeId="Sketcher::SketchObject", State=[],
                             ExpressionEngine=[(".Constraints.W", "SrcDoc#<<Dims>>.Wall")])
    if getter:
        sketch.getExpression = lambda path: "SrcDoc#<<Dims>>.Wall"
    document = SimpleNamespace(Name="DepDoc", Objects=[sketch])
    if entrypoint == "typed":
        result = diagnose_parametric(document, None)
    else:
        result = diagnose_parametric_gui("DepDoc", freecad=SimpleNamespace(getDocument=lambda _: document))
    assert result["expression_issues"] == []


def test_missing_binding_from_an_available_getter_is_still_reported():
    obj = SimpleNamespace(Name="Sketch", TypeId="Sketcher::SketchObject", State=[],
                          ExpressionEngine=[(".Constraints.W", "10 mm")], getExpression=lambda _: None)
    result = diagnose_parametric(SimpleNamespace(Name="DepDoc", Objects=[obj]), None)
    assert result["expression_issues"][0]["issue"] == "missing_binding"
