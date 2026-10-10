"""Round 12: projections contain actual FreeCAD properties only."""
from types import SimpleNamespace
import pytest
from addon.FreeCADMCP.rpc_server.serialize import project_listing_object

pytestmark = pytest.mark.unit


def project(obj, names):
    return project_listing_object(obj, fields=("Name",), include_properties=tuple(names),
                                  include_shape=False, include_view=False)["Properties"]


def test_existing_property_is_projected():
    obj = SimpleNamespace(Name="Box", PropertiesList=["Length"], Length=10)
    assert project(obj, ["Length"]) == {"Length": 10}


def test_missing_properties_and_aliases_are_omitted():
    obj = SimpleNamespace(Name="Sheet", PropertiesList=["Label"], Label="Dimensions", Width=40)
    assert project(obj, ["Label", "Width", "Length"]) == {"Label": "Dimensions"}
