"""Round 12: origin ownership is part of the document tree."""
from types import SimpleNamespace as NS
import pytest
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.assembly_io_actions import get_document_tree

pytestmark = pytest.mark.unit


def tree(objects):
    return get_document_tree(NS(Name="Doc", Objects=objects), root_filter="", max_depth=3,
                             include=["Name"], include_properties=None, selected_nodes=None)["roots"]


def test_group_children_are_owned():
    child = NS(Name="Box")
    assert tree([NS(Name="Part", Group=[child]), child]) == [
        {"Name": "Part", "children": [{"Name": "Box", "children": []}]}]


@pytest.mark.parametrize("kind", ["App::Part", "PartDesign::Body"])
def test_origins_and_features_are_owned(kind):
    axis = NS(Name="XAxis")
    origin = NS(Name="Origin", OriginFeatures=[axis])
    part = NS(Name="Part", TypeId=kind, Group=[], Origin=origin)
    assert tree([part, origin, axis]) == [{"Name": "Part", "children": [
        {"Name": "Origin", "children": [{"Name": "XAxis", "children": []}]}]}]
