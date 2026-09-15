"""Unit tests for PartDesign feature property helpers."""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.rpc_server.rpc_helpers_ops.feature_properties import (
    _set_extrusion_symmetric,
)
from freecad_mcp.template_resources import read_template_text


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


def _load_template_set_extrusion_symmetric():
    namespace: dict = {}
    exec(read_template_text("core/partdesign_extrusion_helper.py.txt"), namespace)
    return namespace["_set_extrusion_symmetric"]


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


def test_template_set_extrusion_symmetric_matches_addon_helper():
    template_helper = _load_template_set_extrusion_symmetric()
    for type_id in ("PartDesign::Pocket", "PartDesign::Pad"):
        addon_feature = _FakeExtrusionFeature(type_id=type_id)
        template_feature = _FakeExtrusionFeature(type_id=type_id)
        assert _set_extrusion_symmetric(addon_feature, True) == template_helper(
            template_feature, True
        )
        assert addon_feature.SideType == template_feature.SideType
        assert addon_feature.Midplane == template_feature.Midplane
