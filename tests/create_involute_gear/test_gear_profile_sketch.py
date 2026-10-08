"""Gear profiles must reach the sketch without hundreds of solves.

``_close_points`` repeats the first point at the end, and OpenCASCADE refuses a
periodic interpolation through a duplicated point. Every gear therefore fell
back to one line segment plus one Coincident constraint per sample, each added
separately, so the sketch re-solved hundreds of times. In a debug build a 24
tooth involute gear held the GIL for minutes and the MCP call timed out.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import gear_actions

pytestmark = pytest.mark.unit


class _Vec:
    def __init__(self, x: float, y: float, z: float = 0.0) -> None:
        self.x, self.y, self.z = x, y, z

    def __sub__(self, other: "_Vec") -> "_Vec":
        return _Vec(self.x - other.x, self.y - other.y, self.z - other.z)

    @property
    def Length(self) -> float:
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)


class _PeriodicBSpline:
    def interpolate(self, Points, PeriodicFlag):
        assert PeriodicFlag is True
        if (Points[0] - Points[-1]).Length < 1e-9:
            raise RuntimeError("BSplCLib::Interpolate")
        self.points = Points


class _Sketch:
    def __init__(self) -> None:
        self.geometry_calls: list[object] = []
        self.constraint_calls: list[object] = []
        self._count = 0

    def addGeometry(self, geometry, construction=False):
        self.geometry_calls.append(geometry)
        if isinstance(geometry, list):
            first = self._count
            self._count += len(geometry)
            return tuple(range(first, self._count))
        self._count += 1
        return self._count - 1

    def addConstraint(self, constraint):
        self.constraint_calls.append(constraint)


def _closed_profile(count: int = 40) -> list[_Vec]:
    points = [_Vec(10 * math.cos(a), 10 * math.sin(a))
              for a in (i * 2 * math.pi / count for i in range(count))]
    gear_actions._close_points(points, 1e-6)
    return points


def _install(monkeypatch, *, bspline: bool) -> None:
    part = SimpleNamespace(LineSegment=lambda p1, p2: ("line", p1, p2))
    if bspline:
        part.BSplineCurve = _PeriodicBSpline
    monkeypatch.setattr(gear_actions, "_part", lambda: part)
    monkeypatch.setattr(gear_actions, "_sketcher",
                        lambda: SimpleNamespace(Constraint=lambda *args: args))


def test_closed_profile_becomes_one_periodic_bspline(monkeypatch):
    _install(monkeypatch, bspline=True)
    points = _closed_profile()
    sketch = _Sketch()

    assert gear_actions._profile_to_sketch(sketch, points, 1e-6) == 1

    assert len(sketch.geometry_calls) == 1
    assert isinstance(sketch.geometry_calls[0], _PeriodicBSpline)
    assert len(sketch.geometry_calls[0].points) == len(points) - 1
    assert sketch.constraint_calls == []


def test_segment_fallback_adds_geometry_and_constraints_in_one_batch(monkeypatch):
    _install(monkeypatch, bspline=False)
    points = _closed_profile()
    sketch = _Sketch()

    assert gear_actions._profile_to_sketch(sketch, points, 1e-6) == len(points) - 1

    assert len(sketch.geometry_calls) == 1
    assert len(sketch.constraint_calls) == 1
    assert len(sketch.constraint_calls[0]) == len(points) - 1
