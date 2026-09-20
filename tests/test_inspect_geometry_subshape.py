"""D-19: ``inspect_geometry(subshape="Face6")`` must return that sub-shape's pose.

The add-on computed ``global_center`` / ``global_normal`` for the requested sub-shape, but the
typed success constructor (and the client parser) rebuilt the result from a fixed key list, so
the call silently returned only the whole object's data.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")

from addon.FreeCADMCP._shared.protocol import inspect_geometry_contract as addon_contract  # noqa: E402
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.inspect_geometry import (  # noqa: E402
    run_inspect_geometry,
)
from freecad_mcp._shared.protocol import inspect_geometry_contract as client_contract  # noqa: E402

pytestmark = pytest.mark.unit


def _collaborators():
    placement = FreeCAD.Placement(FreeCAD.Vector(0, 0, 430), FreeCAD.Rotation())
    shape = Part.makeBox(420, 400, 20, FreeCAD.Vector(-210, -200, 0))
    seat = SimpleNamespace(
        Name="Seat", Label="Seat", TypeId="Part::Feature", Shape=shape.transformed(placement.toMatrix()),
        Placement=FreeCAD.Placement(), getGlobalPlacement=lambda: FreeCAD.Placement(), InList=[],
    )
    document = SimpleNamespace(Name="Chair", Objects=[seat], getObject={"Seat": seat}.get)
    return SimpleNamespace(freecad=SimpleNamespace(getDocument=lambda _name: document))


def _top_face_name() -> str:
    shape = Part.makeBox(420, 400, 20, FreeCAD.Vector(-210, -200, 430))
    for index, face in enumerate(shape.Faces, start=1):
        if abs(face.CenterOfMass.z - 450) < 1e-9:
            return f"Face{index}"
    raise AssertionError("no top face")


def test_addon_returns_the_subshape_pose():
    face = _top_face_name()
    result = run_inspect_geometry(_collaborators(), "Chair", "Seat", face)
    assert result["success"] is True, result
    assert result["subshape"]["name"] == face
    assert result["subshape"]["global_center"] == {"x": 0.0, "y": 0.0, "z": 450.0}
    assert abs(abs(result["subshape"]["global_normal"]["z"]) - 1.0) < 1e-9


def test_whole_object_request_has_no_subshape():
    result = run_inspect_geometry(_collaborators(), "Chair", "Seat", None)
    assert result["success"] is True, result
    assert "subshape" not in result


@pytest.mark.parametrize("contract", [addon_contract, client_contract])
def test_parser_keeps_the_subshape_pose(contract):
    pose = {"name": "Face6", "global_center": {"x": 0.0, "y": 0.0, "z": 450.0},
            "global_normal": {"x": 0.0, "y": 0.0, "z": 1.0}}
    wire = contract.make_inspect_geometry_success(
        "Seat", "Part::Feature", {}, {}, [], {}, {}, subshape=pose
    )
    parsed = contract.parse_inspect_geometry_response(dict(wire))
    assert parsed["success"] is True
    assert parsed["subshape"] == pose
