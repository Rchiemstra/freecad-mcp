"""Unit tests for PartDesign feature property helpers."""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.rpc_server.rpc_helpers_ops.feature_properties import (
    _set_extrusion_symmetric,
)


class _FakeExtrusionFeature:
    """Minimal PartDesign pocket/pad stand-in for SideType mapping tests."""

    def __init__(
        self,
        *,
        type_id: str = "PartDesign::Pocket",
        properties: list[str] | None = None,
        side_type: str = "One side",
        midplane: bool = False,
        length: float = 4.0,
        length2: float = 5.0,
    ):
        self.TypeId = type_id
        self.PropertiesList = properties or [
            "SideType",
            "Midplane",
            "Length",
            "Length2",
            "Reversed",
        ]
        self.SideType = side_type
        self.Midplane = midplane
        self.Length = length
        self.Length2 = length2
        self.Reversed = False


@pytest.mark.parametrize(
    ("type_id",),
    [
        ("PartDesign::Pocket",),
        ("PartDesign::Pad",),
    ],
)
def test_set_extrusion_symmetric_true_sets_sidetype_symmetric(type_id):
    feature = _FakeExtrusionFeature(type_id=type_id)
    result = _set_extrusion_symmetric(feature, True)
    assert result == "SideType"
    assert feature.SideType == "Symmetric"
    assert feature.Midplane is False
    assert feature.Length2 == 5.0


def test_set_extrusion_symmetric_false_sets_sidetype_one_side():
    feature = _FakeExtrusionFeature()
    result = _set_extrusion_symmetric(feature, False)
    assert result == "SideType"
    assert feature.SideType == "One side"
