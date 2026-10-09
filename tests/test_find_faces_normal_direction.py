"""find_faces keeps faces whose normal points the same way as normal_approx.

A pad's top and bottom planes are parallel, so an absolute dot product
returned the bottom face (normal -Z) for a +Z query. Faces are compared
with a signed dot. Edges stay undirected.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.diagnostics_shape_actions import (
    find_subshapes,
)

pytestmark = pytest.mark.unit


class _Vec:
    def __init__(self, x: float, y: float, z: float) -> None:
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)
        self.Length = math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def dot(self, other: _Vec) -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def normalize(self) -> _Vec:
        length = self.Length or 1.0
        return _Vec(self.x / length, self.y / length, self.z / length)

    def __sub__(self, other: _Vec) -> _Vec:
        return _Vec(self.x - other.x, self.y - other.y, self.z - other.z)


class _Rotation:
    def __mul__(self, direction: _Vec) -> _Vec:
        return direction


class _Placement:
    Rotation = _Rotation()

    def __mul__(self, point: _Vec) -> _Vec:
        return point


class Plane:
    pass


class Line:
    pass


class _Face:
    def __init__(self, normal: _Vec, center: _Vec) -> None:
        self.Surface = Plane()
        self.CenterOfMass = center
        self.Area = 200.0
        self.ParameterRange = (0.0, 1.0, 0.0, 1.0)
        self._normal = normal

    def normalAt(self, _u: float, _v: float) -> _Vec:
        return self._normal


class _Edge:
    def __init__(self, direction: _Vec) -> None:
        self.Curve = Line()
        self.Curve.Direction = direction
        self.CenterOfMass = _Vec(0.0, 0.0, 5.0)
        self.Length = 10.0


def _document(kind: str, items: list[object]):
    shape = SimpleNamespace(isNull=lambda: False)
    setattr(shape, kind, items)
    obj = SimpleNamespace(
        Name="Pad",
        Shape=shape,
        getGlobalPlacement=lambda: _Placement(),
    )
    return SimpleNamespace(getObject=lambda name: obj if name == "Pad" else None)


@pytest.fixture
def _vectors(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.diagnostics_shape_actions._vector",
        lambda x, y, z=0.0: _Vec(x, y, z),
    )


def test_positive_z_returns_only_the_top_face(_vectors):
    bottom = _Face(_Vec(0.0, 0.0, -1.0), _Vec(10.0, 5.0, 0.0))
    top = _Face(_Vec(0.0, 0.0, 1.0), _Vec(10.0, 5.0, 10.0))
    payload = find_subshapes(
        _document("Faces", [bottom, top]),
        "Pad",
        "Faces",
        type_filter="Plane",
        normal_approx={"x": 0, "y": 0, "z": 1},
    )

    assert payload["count"] == 1
    face = payload["results"][0]
    assert face["global_center"]["z"] == 10.0
    assert face["global_normal"]["z"] > 0


def test_negative_z_returns_only_the_bottom_face(_vectors):
    bottom = _Face(_Vec(0.0, 0.0, -1.0), _Vec(10.0, 5.0, 0.0))
    top = _Face(_Vec(0.0, 0.0, 1.0), _Vec(10.0, 5.0, 10.0))
    payload = find_subshapes(
        _document("Faces", [bottom, top]),
        "Pad",
        "Faces",
        type_filter="Plane",
        normal_approx={"x": 0, "y": 0, "z": -1},
    )

    assert payload["count"] == 1
    face = payload["results"][0]
    assert face["global_center"]["z"] == 0.0
    assert face["global_normal"]["z"] < 0


def test_edge_direction_query_keeps_both_senses(_vectors):
    upward = _Edge(_Vec(0.0, 0.0, 1.0))
    downward = _Edge(_Vec(0.0, 0.0, -1.0))
    payload = find_subshapes(
        _document("Edges", [upward, downward]),
        "Pad",
        "Edges",
        type_filter="Line",
        normal_approx={"x": 0, "y": 0, "z": 1},
    )

    assert payload["count"] == 2
