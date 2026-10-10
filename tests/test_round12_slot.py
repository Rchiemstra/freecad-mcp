import pytest
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_add_slot import run_sketch_add_slot
from tests.sketch_exec_support import FakeDocument, collaborators

pytestmark = pytest.mark.unit


def slot(width):
    events = []
    doc = FakeDocument(events)
    collab, _ = collaborators(doc, events)
    return run_sketch_add_slot(collab, "Doc", "Sketch", 0, 0, 20, 0, width, False), doc


def test_positive_slot_has_four_edges():
    result, doc = slot(6)
    assert result["success"]
    assert doc.sketch.GeometryCount == 4


@pytest.mark.parametrize("width", [0, -4])
def test_nonpositive_slot_is_rejected_without_geometry(width):
    result, doc = slot(width)
    assert not result["success"]
    assert "width must be greater than zero" in result["error"]
    assert doc.sketch.GeometryCount == 0


def test_slot_has_coincident_and_tangent_joins():
    result, doc = slot(6)
    assert result["success"]
    types = [c.args[0] for c in doc.sketch.Constraints]
    assert all(len(c.args) == 5 for c in doc.sketch.Constraints)
    assert types.count("Tangent") == 4
