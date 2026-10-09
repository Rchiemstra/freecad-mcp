"""get_sketch_diagnostics must return the fields it documents.

The typed handler returned only counts and a conflict flag, so the documented
pre-pad check (fully constrained, closed, which constraints conflict) could
not be made; an under-constrained sketch looked identical to a finished one.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.get_sketch_diagnostics import (
    run_get_sketch_diagnostics,
)

pytestmark = pytest.mark.unit


def _collaborators(sketch):
    document = SimpleNamespace(
        Name="Doc", getObject={"Sketch": sketch}.get, Objects=[sketch]
    )
    return SimpleNamespace(
        freecad=SimpleNamespace(getDocument=lambda name: document if name == "Doc" else None)
    )


def _sketch(**overrides):
    sketch = SimpleNamespace(
        Name="Sketch",
        TypeId="Sketcher::SketchObject",
        GeometryCount=4,
        ConstraintCount=11,
        State=["Up-to-date"],
        DoF=2,
        FullyConstrained=False,
        ConflictingConstraints=[],
        RedundantConstraints=[],
        MalformedConstraints=[],
        Shape=SimpleNamespace(isNull=lambda: False, isClosed=lambda: True),
        solveFailed=lambda: False,
    )
    for key, value in overrides.items():
        setattr(sketch, key, value)
    return sketch


def test_an_under_constrained_sketch_reports_its_freedom():
    result = run_get_sketch_diagnostics(_collaborators(_sketch()), "Doc", "Sketch")

    assert result["success"] is True
    assert result["dof"] == 2
    assert result["fully_constrained"] is False
    assert result["is_closed"] is True
    assert result["state"] == ["Up-to-date"]
    assert result["conflicting_constraints"] == []


def test_a_conflicting_sketch_names_the_constraints():
    sketch = _sketch(DoF=0, ConflictingConstraints=[10, 12], RedundantConstraints=[3])

    result = run_get_sketch_diagnostics(_collaborators(sketch), "Doc", "Sketch")

    assert result["conflicting_constraints"] == [10, 12]
    assert result["redundant_constraints"] == [3]
    assert result["conflict"] is True


def test_an_open_profile_is_reported():
    sketch = _sketch(Shape=SimpleNamespace(isNull=lambda: False, isClosed=lambda: False))

    result = run_get_sketch_diagnostics(_collaborators(sketch), "Doc", "Sketch")

    assert result["is_closed"] is False


def test_a_solid_is_not_reported_as_a_closed_sketch():
    box = SimpleNamespace(
        Name="Box",
        TypeId="Part::Box",
        Shape=SimpleNamespace(isNull=lambda: False, isClosed=lambda: True),
    )
    document = SimpleNamespace(Name="Doc", getObject=lambda name: box if name == "Box" else None)
    collaborators = SimpleNamespace(
        freecad=SimpleNamespace(getDocument=lambda name: document if name == "Doc" else None)
    )

    result = run_get_sketch_diagnostics(collaborators, "Doc", "Box")

    assert result["success"] is False
    assert "not a sketch" in result["error"]


def test_an_empty_sketch_is_not_fully_constrained_or_closed():
    sketch = _sketch(
        GeometryCount=0,
        ConstraintCount=0,
        DoF=0,
        FullyConstrained=True,
        Shape=SimpleNamespace(isNull=lambda: True, isClosed=lambda: True),
    )

    result = run_get_sketch_diagnostics(_collaborators(sketch), "Doc", "Sketch")

    assert result["success"] is True
    assert result["dof"] == 0
    assert result["fully_constrained"] is False
    assert result["is_closed"] is False
    assert result["solver_message"] == "Empty sketch"


def test_an_under_constrained_sketch_explains_the_remaining_freedom():
    result = run_get_sketch_diagnostics(_collaborators(_sketch(DoF=8)), "Doc", "Sketch")

    assert result["dof"] == 8
    assert result["fully_constrained"] is False
    assert result["solver_message"] == "Under-constrained: 8 Degrees of Freedom"


def test_a_missing_shape_is_not_a_closed_profile():
    sketch = _sketch(Shape=None)

    result = run_get_sketch_diagnostics(_collaborators(sketch), "Doc", "Sketch")

    assert result["is_closed"] is False
