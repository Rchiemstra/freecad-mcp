from types import SimpleNamespace as NS
import pytest
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.set_expression import apply_set_expression, build_set_expression_request
from tests.set.test_set_expression import _item

pytestmark = pytest.mark.unit


def bind(unit):
    item = _item("Box")
    item.Length = NS(Unit=NS(Signature=(1, 0, 0, 0, 0, 0, 0, 0)))
    item.evalExpression = lambda expr: NS(Unit=NS(Signature=unit), Value=1200)
    doc = NS(getObject=lambda name: item)
    request = build_set_expression_request("Doc", "Box", "Length", "Dims.Area")
    apply_set_expression(doc, request)
    return item


@pytest.mark.parametrize("unit", [(1, 0, 0, 0, 0, 0, 0, 0), (0,) * 8])
def test_compatible_or_unitless_expression_is_allowed(unit):
    assert bind(unit).getExpression("Length") == "Dims.Area"


def test_area_cannot_bind_a_length():
    with pytest.raises(RuntimeError, match="Unit mismatch") as error:
        bind((2, 0, 0, 0, 0, 0, 0, 0))
    assert error.value.code == "EXPRESSION_UNIT_MISMATCH"
