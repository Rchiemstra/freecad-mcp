from types import SimpleNamespace as NS
import pytest
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.recompute_helpers import collect_invalid_objects

pytestmark = pytest.mark.unit


def errors(state):
    obj = NS(Name="Feature", State=state)
    return collect_invalid_objects(NS(listDocuments=lambda: {"Doc": NS(Objects=[obj])}))


def test_failed_recompute_is_an_error():
    assert errors(["Error", "Touched"])["Doc"][0]["name"] == "Feature"


def test_merely_touched_is_not_an_error():
    assert errors(["Touched"]) == {}
