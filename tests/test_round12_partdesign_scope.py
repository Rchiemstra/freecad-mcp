from types import SimpleNamespace as NS
import pytest
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.create_object import CreateObjectReceipt, read_create_object_result

pytestmark = pytest.mark.unit


def inspect(base):
    target = NS(Name="Base")
    feature = NS(Name="Thickness", Label="Thickness", TypeId="PartDesign::Thickness", Base=target if base else None)
    doc = NS(getObject=lambda name: feature if name == feature.Name else target)
    receipt = CreateObjectReceipt(feature.Name, feature, feature.TypeId, (("Base", target),))
    return read_create_object_result(doc, receipt)


def test_kept_base_succeeds():
    assert inspect(True).name == "Thickness"


def test_dropped_base_explains_body_scope():
    with pytest.raises(RuntimeError, match="links are out of scope.*inside the body"):
        inspect(False)
