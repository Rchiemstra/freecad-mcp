import pytest
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.create_object import run_create_object
from tests.typed_rpc_fakes import FakeDocument, collaborators

pytestmark = pytest.mark.unit


def test_known_type_creates_object():
    events = []
    doc = FakeDocument(events)
    collab, _ = collaborators(doc, events)
    assert run_create_object(collab, "Doc", {"Type": "Part::Box", "Name": "Box"})["success"]


def test_unknown_type_has_public_error():
    events = []
    doc = FakeDocument(events)
    def add(*args):
        raise ModuleNotFoundError("No module named 'Not'")
    doc.addObject = add
    collab, _ = collaborators(doc, events)
    result = run_create_object(collab, "Doc", {"Type": "Not::AType", "Name": "Nope"})
    assert not result["success"]
    assert result["error_code"] == "UNKNOWN_OBJECT_TYPE"
    assert result["error"] == "Unknown object type: Not::AType"
