from types import SimpleNamespace as NS
import pytest
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.diagnostics_shape_actions import find_subshapes

pytestmark = pytest.mark.unit


class Translation:
    Rotation = NS(multVec=lambda v: v)
    def __init__(self, x=0):
        self.x = x
    def __mul__(self, other):
        if isinstance(other, Translation):
            return Translation(self.x + other.x)
        return NS(x=other.x + self.x, y=other.y, z=other.z)
    def inverse(self):
        return Translation(-self.x)


def face_center(local_x, parent_x):
    face = NS(CenterOfMass=NS(x=local_x + 5, y=5, z=10), Area=100)
    obj = NS(Name="Box", Placement=Translation(local_x),
             Shape=NS(isNull=lambda: False, Faces=[face]),
             getGlobalPlacement=lambda: Translation(local_x + parent_x))
    return find_subshapes(NS(getObject=lambda name: obj), "Box", "Faces")["results"][0]["global_center"]


def test_shape_in_translated_parent():
    assert face_center(0, 100)["x"] == 105


def test_placed_shape_in_parent():
    assert face_center(20, 100)["x"] == 125
