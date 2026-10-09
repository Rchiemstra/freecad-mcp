"""A helical gear must be the involute tooth form, swept on the real lead."""

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
        self.points = Points


class _Sketch:
    def __init__(self) -> None:
        self.Name = ""
        self.geometry_calls: list[object] = []

    def addGeometry(self, geometry, construction=False):
        self.geometry_calls.append(geometry)
        return 0

    def addConstraint(self, constraint):
        return None


class _Body:
    Name = "HelicalA_Body"
    Origin = None

    def __init__(self) -> None:
        self.made: list[tuple[str, object]] = []

    def newObject(self, type_name: str, name: str):
        obj = _Sketch() if "Sketch" in type_name else SimpleNamespace(Name=name)
        obj.Name = name
        self.made.append((type_name, obj))
        return obj


def _install(monkeypatch) -> _Body:
    body = _Body()
    part = SimpleNamespace(
        BSplineCurve=_PeriodicBSpline,
        Circle=lambda center, normal, radius: SimpleNamespace(
            kind="circle", center=center, radius=radius
        ),
        LineSegment=lambda p1, p2: ("line", p1, p2),
    )
    monkeypatch.setattr(gear_actions, "_part", lambda: part)
    monkeypatch.setattr(
        gear_actions, "_sketcher", lambda: SimpleNamespace(Constraint=lambda *args: args)
    )
    monkeypatch.setattr(gear_actions, "_vector", lambda x, y, z=0.0: _Vec(x, y, z))
    return body


def _build(body: _Body, helix_angle: float):
    document = SimpleNamespace(addObject=lambda _type, _name: body)
    gear_actions.create_helical_gear(
        document,
        gear_name="HelicalA",
        teeth=16,
        module=1.0,
        width=6.0,
        helix_angle=helix_angle,
        pressure_angle=20.0,
        bore_diameter=0.0,
        clearance=0.25,
        backlash=0.0,
        samples_per_flank=5,
        body_name=None,
    )
    feature = next(obj for type_name, obj in body.made if type_name == "PartDesign::AdditiveHelix")
    sketch = next(obj for type_name, obj in body.made if "Sketch" in type_name)
    return sketch, feature


def test_helical_profile_spans_the_involute_and_uses_the_axial_lead(monkeypatch):
    body = _install(monkeypatch)
    sketch, feature = _build(body, 15.0)

    curve = sketch.geometry_calls[0]
    assert isinstance(curve, _PeriodicBSpline)
    radii = [math.hypot(point.x, point.y) for point in curve.points]
    assert max(radii) == pytest.approx(9.0, abs=0.2)
    assert min(point.x for point in curve.points) < 0
    lead = math.pi * 16.0 / math.tan(math.radians(15.0))
    assert feature.Pitch == pytest.approx(lead, rel=1e-6)
    assert feature.Reversed is False

    negative_body = _install(monkeypatch)
    _sketch, negative = _build(negative_body, -15.0)
    assert negative.Pitch == pytest.approx(lead, rel=1e-6)
    assert negative.Pitch > 0
    assert negative.Reversed is True
