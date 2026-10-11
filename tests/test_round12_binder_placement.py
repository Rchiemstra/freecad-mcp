import pytest
from types import SimpleNamespace as NS
from tests.create_subshape_binder.test_create_subshape_binder import _Document, _seed
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.create_subshape_binder import apply_create_subshape_binder, build_create_subshape_binder_request

pytestmark = pytest.mark.unit


class Placement:
    def __init__(self, x=0):
        self.Base = NS(x=x,y=0,z=0)
    def inverse(self):
        return Placement(-self.Base.x)
    def __mul__(self, other):
        return Placement(self.Base.x + other.Base.x)


def binder(relative, parent_x=0):
    doc = _Document([]); _seed(doc)
    doc.objects['Seed'].Placement = Placement(20)
    doc.objects['Seed'].getGlobalPlacement = lambda:Placement(parent_x + 20)
    request = build_create_subshape_binder_request('Doc', 'Binder', 'Seed', None, None, None, relative, True, 'error')
    return apply_create_subshape_binder(doc, request).item


def test_frozen_coordinate_binding_keeps_source_placement():
    assert binder(False).Placement.Base.x == 20


def test_relative_binding_does_not_repeat_source_placement():
    assert binder(True).Placement.Base.x == 0


def test_relative_binding_applies_source_parent_only():
    assert binder(True, parent_x=100).Placement.Base.x == 100
