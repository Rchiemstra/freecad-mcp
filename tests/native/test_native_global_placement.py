"""``read_global_placement`` must not call the deprecated getter.

A Pad in a Body in an App::Part, each with a non-identity placement, reports
the composed global placement through ``GeoFeature.getGlobalPlacementOf``.
"""

from __future__ import annotations

import warnings

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.world_shape_actions import (  # noqa: E402
    read_global_placement,
)

pytestmark = pytest.mark.core


def test_pad_in_body_in_part_reads_global_placement_without_deprecation():
    doc = FreeCAD.newDocument("MCPGlobalPlacement")
    try:
        part = doc.addObject("App::Part", "Part")
        part.Placement = FreeCAD.Placement(
            FreeCAD.Vector(10, 0, 0),
            FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), 20),
        )
        body = part.newObject("PartDesign::Body", "Body")
        body.Placement = FreeCAD.Placement(
            FreeCAD.Vector(0, 7, 0),
            FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 15),
        )
        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Shape = Part.makeBox(4, 4, 4)
        pad.Placement = FreeCAD.Placement(
            FreeCAD.Vector(1, 2, 3),
            FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 10),
        )
        doc.recompute()
        expected = part.Placement * body.Placement * pad.Placement
        identity = FreeCAD.Placement()
        assert not part.Placement.isSame(identity, 1e-7)
        assert not body.Placement.isSame(identity, 1e-7)
        assert not pad.Placement.isSame(identity, 1e-7)
        assert not expected.isSame(pad.Placement, 1e-7)

        # Record the warning as well as treating it as an error: a caught
        # DeprecationWarning would otherwise still return a placement.
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            got = read_global_placement(pad)
        assert not [
            item
            for item in caught
            if "getGlobalPlacement" in str(item.message)
        ], caught
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            again = read_global_placement(pad)

        assert got.isSame(expected, 1e-7)
        assert again.isSame(expected, 1e-7)
    finally:
        FreeCAD.closeDocument(doc.Name)
