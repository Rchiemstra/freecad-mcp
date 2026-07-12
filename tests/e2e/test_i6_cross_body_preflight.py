"""I6 e2e: creating a cross-body datum plane surfaces a PREFLIGHT WARNING when
the support lives in a different body with a non-identity placement (the P1
risk), against a live FreeCAD.
"""
from __future__ import annotations

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")
Sketcher = pytest.importorskip("Sketcher")

from freecad_mcp.operations.p7_assembly import create_datum_plane_operation  # noqa: E402
from tests.e2e._helpers import find_face, make_padded_circle, tool_response_text  # noqa: E402

pytestmark = pytest.mark.e2e


def _text(response) -> str:
    return tool_response_text(response)


def test_cross_body_datum_creation_warns(freecad_session):
    doc = freecad_session.doc

    body_b = doc.addObject("PartDesign::Body", "SourceBody")
    _, pad = make_padded_circle(body_b, radius=5, length=5, plane_label="XY_Plane")
    # Give the body its non-identity placement only after the sketch/pad exist:
    # on this FreeCAD the attacher writes the origin plane's GLOBAL placement
    # into the body-local sketch placement at attach time, so attaching inside
    # an already-moved body double-applies the body offset (geometry lands at
    # 2x the placement). Moving the body afterwards keeps the feature body-local
    # and still gives the cross-body scenario this test needs.
    body_b.Placement.Base = FreeCAD.Vector(0, 0, 10)  # non-identity placement
    doc.recompute()
    top = find_face(pad, normal=(0, 0, 1), center=(0, 0, 15), tol=0.5)
    assert top, "could not locate the pad top face"

    body_a = doc.addObject("PartDesign::Body", "DatumBody")

    resp = create_datum_plane_operation(
        freecad_session, True, doc.Name, "CrossDatum", body_a.Name,
        mode="offset_from_face", source_ref=f"{pad.Name}:{top}",
        map_mode="FlatFace",
    )
    text = _text(resp)
    assert "PREFLIGHT WARNING" in text
    assert "CrossDatum" in text
    assert body_b.Name in text
