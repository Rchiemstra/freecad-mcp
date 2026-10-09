"""Radius and Diameter only make sense on circles and arcs.

sketch_constrain_radius on a rectangle's line was added, FreeCAD printed
"Sketcher constraint number 1 is malformed!" and "The Sketch has malformed
constraints!", and the call failed only afterwards.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_add_constraint import (
    run_sketch_add_constraint,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_constrain_radius import (
    run_sketch_constrain_radius,
)
from tests.sketch_exec_support import FakeDocument, collaborators

pytestmark = pytest.mark.unit


def _document(events, type_id):
    document = FakeDocument(events)
    document.sketch.Geometry.append(SimpleNamespace(TypeId=type_id, Construction=False))
    events.clear()
    return document


def _radius(collab):
    return run_sketch_constrain_radius(collab, "Doc", "Sketch", 0, 5.0, None)


def _add(kind):
    return lambda collab: run_sketch_add_constraint(
        collab, "Doc", "Sketch", [{"type": kind, "geo": 0, "value": 5.0}]
    )


@pytest.mark.parametrize("run", [_radius, _add("Radius"), _add("Diameter")])
def test_a_line_is_rejected_before_the_constraint_is_added(run):
    events: list[str] = []
    document = _document(events, "Part::GeomLineSegment")
    collab, _api = collaborators(document, events)

    result = run(collab)

    assert result["success"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"
    assert "circle or arc" in result["error"] and "Part::GeomLineSegment" in result["error"]
    assert document.sketch.ConstraintCount == 0
    assert "commit" not in events


@pytest.mark.parametrize("type_id", ["Part::GeomCircle", "Part::GeomArcOfCircle"])
@pytest.mark.parametrize("run", [_radius, _add("Radius"), _add("Diameter")])
def test_circles_and_arcs_are_accepted(run, type_id):
    events: list[str] = []
    document = _document(events, type_id)
    collab, _api = collaborators(document, events)

    result = run(collab)

    assert result["success"] is True, result
