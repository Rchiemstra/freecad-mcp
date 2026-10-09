"""Measurements must work on whole single-edge objects and faces.

``resolve_global_shape`` returns a generic ``Part.Shape`` copy, which has
neither ``tangentAt`` nor ``CenterOfMass``. ``measure_angle("LineA", ...)`` on a
Part::Line therefore failed with "edge does not support tangentAt" (also the
message for a Face ref), and ``center_of_mass`` on a Part::Line failed with
"Object has no CenterOfMass".
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import measure_io_actions
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.typed_runtime import (
    TypedMutationError,
)

pytestmark = pytest.mark.unit


class _Vec:
    def __init__(self, x: float, y: float, z: float = 0.0) -> None:
        self.x, self.y, self.z = x, y, z

    @property
    def Length(self) -> float:
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)

    def dot(self, other: _Vec) -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z


def _edge(direction, center=(0, 0, 0), length=1.0):
    return SimpleNamespace(
        ShapeType="Edge",
        FirstParameter=0.0,
        tangentAt=lambda _p: _Vec(*direction),
        CenterOfMass=_Vec(*center),
        Length=length,
    )


def _face(center, area):
    return SimpleNamespace(ShapeType="Face", CenterOfMass=_Vec(*center), Area=area)


def _generic(shape_type, *, edges=(), faces=(), solids=()):
    """A ``Part.Shape`` copy: sub-shape lists, no type-specific API."""

    return SimpleNamespace(
        ShapeType=shape_type,
        Edges=list(edges),
        Faces=list(faces),
        Solids=list(solids),
        Vertexes=[],
    )


@pytest.fixture
def document(monkeypatch):
    shapes = {
        "LineA": _generic("Edge", edges=[_edge((0, 1, 0), center=(0, 50, 0), length=100)]),
        "LineB": _generic("Edge", edges=[_edge((1, 0, 0))]),
        "Box": _generic(
            "Solid",
            edges=[_edge((1, 0, 0)) for _ in range(12)],
            faces=[_face((0, 0, 0), 1.0) for _ in range(6)],
        ),
        "Plates": _generic(
            "Compound",
            edges=[_edge((1, 0, 0)) for _ in range(8)],
            faces=[_face((0, 0, 0), 1.0), _face((4, 0, 0), 3.0)],
        ),
        "Wire": _generic(
            "Wire",
            edges=[
                _edge((1, 0, 0), center=(1, 0, 0), length=2.0),
                _edge((0, 1, 0), center=(2, 3, 0), length=6.0),
            ],
        ),
    }
    objects = {name: SimpleNamespace(Name=name, Label=name) for name in shapes}
    monkeypatch.setattr(
        measure_io_actions,
        "resolve_global_shape",
        lambda obj: (shapes[obj.Name], {}),
    )
    monkeypatch.setattr(measure_io_actions, "_vector", _Vec)
    return SimpleNamespace(getObject=objects.get)


def test_subelement_edge_refs_still_measure(document):
    result = measure_io_actions.measure_angle(document, "LineA:Edge1", "Box:Edge1")

    assert result["angle_deg"] == 90.0


def test_bare_single_edge_objects_measure(document):
    result = measure_io_actions.measure_angle(document, "LineA", "LineB")

    assert result["angle_deg"] == 90.0


@pytest.mark.parametrize(
    "ref, fragment",
    [
        ("Box:Face1", "not an edge"),
        ("Box", "Box:EdgeN"),
        ("Box:Edge13", "out of range"),
        ("Box:Edge0", "out of range"),
        ("Box:Edgefoo", "not an edge"),
    ],
)
def test_non_edge_refs_are_invalid_arguments(document, ref, fragment):
    with pytest.raises(TypedMutationError) as caught:
        measure_io_actions.measure_angle(document, ref, "LineB")

    assert caught.value.code == "INVALID_ARGUMENT"
    assert fragment in str(caught.value)


def test_center_of_mass_of_a_line(document):
    result = measure_io_actions.center_of_mass(document, "LineA")

    assert (result["x"], result["y"], result["z"]) == (0.0, 50.0, 0.0)
    assert result["method"] == "edge"


def test_center_of_mass_of_faces_is_area_weighted(document):
    result = measure_io_actions.center_of_mass(document, "Plates")

    assert result["x"] == 3.0
    assert result["method"] == "face"


def test_center_of_mass_of_a_wire_is_length_weighted(document):
    result = measure_io_actions.center_of_mass(document, "Wire")

    assert (result["x"], result["y"]) == (1.75, 2.25)
    assert result["method"] == "edge"
