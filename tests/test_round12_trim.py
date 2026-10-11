from types import SimpleNamespace as NS
import pytest
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_trim import run_sketch_trim
from tests.sketch_exec_support import FakeDocument, collaborators

pytestmark = pytest.mark.unit


def trim(error=None):
    events = []
    doc = FakeDocument(events)
    doc.sketch.addGeometry(NS(), False)
    def operation(*args):
        if error:
            raise RuntimeError(error)
    doc.sketch.trim = operation
    collab, _ = collaborators(doc, events)
    return run_sketch_trim(collab, "Doc", "Sketch", 0, 5, 5)


def test_successful_trim():
    assert trim()["success"]


def test_missing_intersection_explains_failure():
    result = trim("18Standard_NullValue")
    assert not result["success"]
    assert result["error_code"] == "TRIM_NO_INTERSECTION"
    assert "no intersection near the trim point" in result["error"]
