"""Placement codec tests with FreeCAD-accurate angle-unit semantics.

FreeCAD contracts (verified against ``src/Base/RotationPyImp.cpp``):

* ``FreeCAD.Rotation(axis, angle)`` takes **degrees** (converted with toRadians).
* ``rotation.Angle`` returns **radians** (internal ``_angle``).
* Public MCP JSON ``Rotation.Angle`` is **degrees**.

A fake that stores the constructor argument unchanged would hide the bug this
suite exists to catch.
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import MagicMock

import FreeCAD
import pytest

from freecad_mcp.template_resources import read_template_text
from tests.helpers.runtime_bootstrap import ensure_freecad_stub

ensure_freecad_stub()

from addon.FreeCADMCP.rpc_server.placement_codec import (  # noqa: E402
    ANGLE_DEG_TOL,
    dict_to_placement,
    freecad_angle_from_degrees,
    placement_to_dict,
)
from addon.FreeCADMCP.rpc_server.property_mapper import set_object_property  # noqa: E402
from addon.FreeCADMCP.rpc_server.serialize import serialize_value  # noqa: E402


GENERATED_PLACEMENT_HELPERS = read_template_text(
    "parametric/placement_helpers.py.txt"
)


class _FakeVector:
    def __init__(self, x=0, y=0, z=0):
        self.x, self.y, self.z = float(x), float(y), float(z)


class _FakeRotation:
    """Models FreeCAD: ctor angle is degrees; ``.Angle`` is radians."""

    def __init__(self, *args):
        if len(args) == 0:
            self.Axis = _FakeVector(0, 0, 1)
            self._angle_rad = 0.0
            return
        if len(args) == 2:
            axis, angle_deg = args
            self.Axis = axis if isinstance(axis, _FakeVector) else _FakeVector(
                getattr(axis, "x", 0), getattr(axis, "y", 0), getattr(axis, "z", 1)
            )
            self._angle_rad = freecad_angle_from_degrees(angle_deg)
            return
        if len(args) == 3:
            # Yaw, Pitch, Roll — FreeCAD stores/returns these in degrees via
            # dedicated properties; for axis-angle tests we only need Angle.
            self.Axis = _FakeVector(0, 0, 1)
            self._angle_rad = freecad_angle_from_degrees(args[0])
            self._ypr = tuple(float(a) for a in args)
            return
        raise TypeError(f"Unexpected Rotation args: {args!r}")

    @property
    def Angle(self) -> float:
        return self._angle_rad


class _FakePlacement:
    def __init__(self, base=None, rotation=None):
        self.Base = base if base is not None else _FakeVector()
        self.Rotation = rotation if rotation is not None else _FakeRotation()


@pytest.fixture(autouse=True)
def _freecad_semantic_types(monkeypatch):
    monkeypatch.setattr(FreeCAD, "Placement", _FakePlacement)
    monkeypatch.setattr(FreeCAD, "Vector", _FakeVector)
    monkeypatch.setattr(FreeCAD, "Rotation", _FakeRotation)
    console = MagicMock()
    monkeypatch.setattr(FreeCAD, "Console", console)
    yield console


def test_ninety_degree_round_trip_preserves_degrees():
    """Regression: serialize used to emit radians into a degree constructor."""
    original = {
        "Base": {"x": 1.0, "y": 2.0, "z": 3.0},
        "Rotation": {"Axis": {"x": 0.0, "y": 0.0, "z": 1.0}, "Angle": 90.0},
    }
    placement = dict_to_placement(original)
    # Constructor consumed 90° → internal storage is π/2 rad.
    assert abs(placement.Rotation.Angle - (math.pi / 2)) < ANGLE_DEG_TOL
    assert abs(placement.Base.z - 3.0) < ANGLE_DEG_TOL

    public = placement_to_dict(placement)
    assert abs(public["Rotation"]["Angle"] - 90.0) < 1e-9
    assert abs(public["Base"]["x"] - 1.0) < ANGLE_DEG_TOL

    restored = dict_to_placement(public)
    assert abs(restored.Rotation.Angle - (math.pi / 2)) < ANGLE_DEG_TOL
    assert abs(restored.Base.z - 3.0) < ANGLE_DEG_TOL


def test_serialize_value_emits_degrees_not_radians():
    placement = dict_to_placement(
        {
            "Base": {"x": 0, "y": 0, "z": 0},
            "Rotation": {"Axis": {"x": 0, "y": 0, "z": 1}, "Angle": 90},
        }
    )
    blob = serialize_value(placement)
    assert abs(blob["Rotation"]["Angle"] - 90.0) < 1e-9
    # Pre-fix bug emitted ~1.570796 (radians as if degrees).
    assert blob["Rotation"]["Angle"] > 10.0


def test_buggy_radian_passthrough_would_fail_this_assertion():
    """Guard: if serialize forgets rad→deg, the public Angle collapses to ~1.57."""
    placement = _FakePlacement(
        _FakeVector(0, 0, 0),
        _FakeRotation(_FakeVector(0, 0, 1), 90),
    )
    # Simulate the old bug: emit Rotation.Angle (radians) as public Angle.
    buggy = {
        "Base": {"x": 0.0, "y": 0.0, "z": 0.0},
        "Rotation": {
            "Axis": {"x": 0.0, "y": 0.0, "z": 1.0},
            "Angle": placement.Rotation.Angle,  # radians wrongly treated as degrees
        },
    }
    collapsed = dict_to_placement(buggy)
    assert abs(collapsed.Rotation.Angle - freecad_angle_from_degrees(90)) > 0.1


def test_attachment_offset_translation_and_rotation_via_set_object_property():
    obj = SimpleNamespace(
        PropertiesList=["AttachmentOffset"],
        AttachmentOffset=_FakePlacement(),
    )
    set_object_property(
        MagicMock(),
        obj,
        {
            "AttachmentOffset": {
                "Base": {"x": 4.0, "y": 5.0, "z": 6.0},
                "Rotation": {"Axis": {"x": 0, "y": 0, "z": 1}, "Angle": 90},
            }
        },
    )
    assert abs(obj.AttachmentOffset.Base.x - 4.0) < ANGLE_DEG_TOL
    assert abs(obj.AttachmentOffset.Base.z - 6.0) < ANGLE_DEG_TOL
    assert abs(obj.AttachmentOffset.Rotation.Angle - math.pi / 2) < ANGLE_DEG_TOL
    public = placement_to_dict(obj.AttachmentOffset)
    assert abs(public["Rotation"]["Angle"] - 90.0) < 1e-9


def test_set_object_property_surfaces_assignment_failures(_freecad_semantic_types):
    class _BoomObj:
        PropertiesList: ClassVar[list[str]] = ["Length"]

        @property
        def Length(self):
            return 1.0

        @Length.setter
        def Length(self, value):
            raise TypeError("cannot assign dict to Length")

    with pytest.raises(ValueError, match="Failed to set property: Length"):
        set_object_property(MagicMock(), _BoomObj(), {"Length": {"bad": True}})
    assert _freecad_semantic_types.PrintError.called


def test_generated_helpers_match_codec_round_trip():
    """Generated execute_code helpers must share the degree contract."""
    ns: dict = {"FreeCAD": FreeCAD, "math": math}
    exec(GENERATED_PLACEMENT_HELPERS, ns)  # noqa: S102
    payload = {
        "Base": {"x": 1.0, "y": 0.0, "z": 12.5},
        "Rotation": {"Axis": {"x": 0.0, "y": 0.0, "z": 1.0}, "Angle": 90.0},
    }
    via_codec = placement_to_dict(dict_to_placement(payload))
    via_generated = ns["_mcp_placement_to_dict"](ns["_mcp_dict_to_placement"](payload))
    assert abs(via_codec["Rotation"]["Angle"] - via_generated["Rotation"]["Angle"]) < 1e-9
    assert abs(via_codec["Base"]["z"] - via_generated["Base"]["z"]) < ANGLE_DEG_TOL
    assert abs(via_generated["Rotation"]["Angle"] - 90.0) < 1e-9


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {"Base": "not-a-vector"},
        {"Rotation": ["not", "a", "rotation"]},
        {"Rotation": {"Axis": "not-a-vector", "Angle": 90}},
    ],
)
def test_generated_helpers_match_codec_validation(payload):
    """Both routes must reject malformed values instead of changing geometry."""
    ns: dict = {"FreeCAD": FreeCAD}
    exec(GENERATED_PLACEMENT_HELPERS, ns)  # noqa: S102

    with pytest.raises(TypeError):
        dict_to_placement(payload)
    with pytest.raises(TypeError):
        ns["_mcp_dict_to_placement"](payload)
