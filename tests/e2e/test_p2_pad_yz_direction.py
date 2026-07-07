"""P2: a pad on a non-XY (YZ / datum) sketch silently extrudes in the wrong
global direction.

A sketch attached to the body's YZ_Plane (normal +X) and padded must extrude
along +X. FreeCAD silently extrudes along a different global axis (observed
-Y) and marks the feature Up-to-date, producing wrong geometry with no error.

Status doc: "best first issue". No exact solved upstream issue found.
"""
from __future__ import annotations

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")
Sketcher = pytest.importorskip("Sketcher")

from tests.e2e._helpers import make_padded_circle

pytestmark = [
    pytest.mark.core,
    pytest.mark.xfail(
        strict=True,
        reason="FreeCAD: pad on YZ_Plane extrudes along wrong global axis, no error",
    ),
]


def test_pad_on_yz_plane_extrudes_along_sketch_normal(freecad_session):
    doc = freecad_session.doc
    body = doc.addObject("PartDesign::Body", "PadBody")
    # Identity placement; sketch on YZ_Plane whose normal is global +X.
    _, pad = make_padded_circle(body, radius=2, length=1, plane_label="YZ_Plane")
    bbox = pad.Shape.BoundBox
    # Expected: extrusion along +X by 1 mm; circle r=2 in the YZ plane.
    assert abs(bbox.XMin - 0.0) <= 1e-3 and abs(bbox.XMax - 1.0) <= 1e-3, (
        f"pad X extent {bbox.XMin}..{bbox.XMax} != 0..1 (extrusion not along +X)"
    )
    assert abs(bbox.YMin - (-2.0)) <= 1e-3 and abs(bbox.YMax - 2.0) <= 1e-3, (
        f"pad Y extent {bbox.YMin}..{bbox.YMax} != -2..2"
    )
    assert abs(bbox.ZMin - (-2.0)) <= 1e-3 and abs(bbox.ZMax - 2.0) <= 1e-3, (
        f"pad Z extent {bbox.ZMin}..{bbox.ZMax} != -2..2"
    )
