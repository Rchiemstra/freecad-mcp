"""Fillet and chamfer must reject sub-element refs the base shape lacks.

A live-GUI stress run created ``fillet_feature(edge_refs=["Edge9999"])`` on a
Pad with 12 edges: the feature was added, the recompute logged
``<Exception> Invalid edge link`` and the caller saw a recompute failure. A
reference that cannot exist is an argument error and must be rejected before
anything is created.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.chamfer_feature import (
    run_chamfer_feature,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.fillet_feature import (
    run_fillet_feature,
)
from tests.typed_feature_fakes import FeatureDocument, collaborators, prepare_document

pytestmark = pytest.mark.unit


def _fillet(collab, refs, size=1.0):
    return run_fillet_feature(collab, "Doc", "Pad", "Fillet", size, refs, None)


def _chamfer(collab, refs, size=1.0):
    return run_chamfer_feature(collab, "Doc", "Pad", "Chamfer", size, refs, None)


def _box_document(events):
    document = FeatureDocument(events)
    prepare_document("edge_feature", document)
    document.objects["Pad"].Shape = SimpleNamespace(
        isNull=lambda: False,
        Faces=[object()] * 6,
        Edges=[object()] * 12,
        Vertexes=[object()] * 8,
        Volume=1.0,
        BoundBox=SimpleNamespace(DiagonalLength=50.0),
    )
    return document


@pytest.mark.parametrize("run", [_fillet, _chamfer])
@pytest.mark.parametrize("refs", [["Edge1"], ["Edge12", "Face6"], ["Vertex8"]])
def test_existing_subelements_are_applied(run, refs):
    events: list[str] = []
    document = _box_document(events)
    collab, _api = collaborators(document, events)

    result = run(collab, refs)

    assert result["success"] is True
    assert "commit" in events


@pytest.mark.parametrize("run", [_fillet, _chamfer])
@pytest.mark.parametrize(
    "refs, missing",
    [
        (["Edge9999"], "Edge9999"),
        (["Edge1", "Edge13"], "Edge13"),
        (["Edge0"], "Edge0"),
        (["Face7"], "Face7"),
        (["Vertex9"], "Vertex9"),
    ],
)
def test_missing_subelements_are_rejected_before_creation(run, refs, missing):
    events: list[str] = []
    document = _box_document(events)
    collab, _api = collaborators(document, events)

    result = run(collab, refs)

    assert result["success"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"
    assert missing in result["error"]
    assert "Pad" in result["error"]
    assert document.add_calls == 0
    assert "recompute" not in events
    assert "commit" not in events


@pytest.mark.parametrize("run, field", [(_fillet, "radius"), (_chamfer, "size")])
def test_a_size_beyond_the_whole_part_is_rejected_before_creation(run, field):
    """chamfer_feature(size=5000) on a small Pad leaked "BRep_API: command not done"."""

    events: list[str] = []
    document = _box_document(events)
    collab, _api = collaborators(document, events)

    result = run(collab, ["Edge1"], size=5000.0)

    assert result["success"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"
    assert f"{field} 5000" in result["error"] and "'Pad'" in result["error"]
    assert document.add_calls == 0
