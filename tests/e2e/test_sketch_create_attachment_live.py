"""Live FreeCAD regression for create-time origin-plane attachment."""

from __future__ import annotations

import math

import pytest

FreeCAD = pytest.importorskip("FreeCAD")

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_gui_create import (  # noqa: E402
    sketch_create_gui,
)
from addon.FreeCADMCP.rpc_server.placement_codec import dict_to_placement  # noqa: E402

pytestmark = pytest.mark.e2e


def test_xz_plane_name_and_offset_survive_live_recompute():
    doc = FreeCAD.newDocument("MCP_CreateAttachmentLive")
    try:
        doc.addObject("PartDesign::Body", "Body")
        result = sketch_create_gui(
            doc.Name,
            "SketchXZ",
            "Body",
            "XZ_Plane",
            {
                "Base": {"x": 0.0, "y": 0.0, "z": 25.0},
                "Rotation": {
                    "Axis": {"x": 0.0, "y": 0.0, "z": 1.0},
                    "Angle": 15.0,
                },
            },
            freecad=FreeCAD,
            dict_to_placement=dict_to_placement,
        )

        assert result is True
        sketch = doc.getObject("SketchXZ")
        assert sketch.MapMode == "FlatFace"
        assert sketch.AttachmentSupport[0][0].Name == "XZ_Plane"
        assert math.isclose(sketch.AttachmentOffset.Base.z, 25.0, abs_tol=1e-8)
        assert math.isclose(
            math.degrees(sketch.AttachmentOffset.Rotation.Angle),
            15.0,
            abs_tol=1e-8,
        )

        doc.recompute()
        assert sketch.MapMode == "FlatFace"
        assert sketch.AttachmentSupport[0][0].Name == "XZ_Plane"
    finally:
        FreeCAD.closeDocument(doc.Name)
