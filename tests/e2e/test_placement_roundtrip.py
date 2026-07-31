"""Live FreeCAD Placement round-trip (skipped when FreeCAD is unavailable)."""

from __future__ import annotations

import math

import pytest

pytestmark = [pytest.mark.core, pytest.mark.e2e]


def test_live_placement_serialize_reapply_preserves_90deg_rotation(freecad_session):
    """Requires a real FreeCAD interpreter — not evidence when skipped."""
    import FreeCAD

    from addon.FreeCADMCP.rpc_server.placement_codec import (
        dict_to_placement,
        placement_to_dict,
    )
    from addon.FreeCADMCP.rpc_server.serialize import serialize_value

    doc = FreeCAD.newDocument("McpPlacementRoundTrip")
    try:
        obj = doc.addObject("Part::Box", "Box")
        obj.Placement = FreeCAD.Placement(
            FreeCAD.Vector(1, 2, 3),
            FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 90),
        )
        public = serialize_value(obj.Placement)
        assert abs(public["Rotation"]["Angle"] - 90.0) < 1e-6
        assert abs(obj.Placement.Rotation.Angle - math.pi / 2) < 1e-9

        reapplied = dict_to_placement(public)
        obj.Placement = reapplied
        again = placement_to_dict(obj.Placement)
        assert abs(again["Rotation"]["Angle"] - 90.0) < 1e-6
        assert abs(again["Base"]["z"] - 3.0) < 1e-9
    finally:
        FreeCAD.closeDocument(doc.Name)
