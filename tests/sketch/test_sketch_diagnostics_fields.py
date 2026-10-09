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
