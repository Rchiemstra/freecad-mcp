"""I1 e2e: preview_attachment flags the P1 cross-body placement-drop risk
against a live FreeCAD.

The diagnostic must report ``source_body_placement_dropped: True`` for a datum
in Body A attached to a face of a feature in Body B, when Body B has a
non-identity placement. It must also surface a structured diff (signed distance
+ normal angle) between the datum and its support face.
"""
from __future__ import annotations

import json

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")
Sketcher = pytest.importorskip("Sketcher")

from freecad_mcp.operations.diagnostics import preview_attachment_operation
from tests.e2e._helpers import find_face, make_padded_circle

pytestmark = pytest.mark.e2e


def _payload(response) -> dict:
    text = "".join(item.text for item in response if hasattr(item, "text"))
    if "Output:" in text:
        text = text.split("Output:", 1)[1].strip()
    return json.loads(text.splitlines()[-1])


def test_preview_attachment_flags_cross_body_drop(freecad_session):
    doc = freecad_session.doc

    body_b = doc.addObject("PartDesign::Body", "SourceBody")
    body_b.Placement.Base = FreeCAD.Vector(0, 0, 10)  # non-identity placement
    _, pad = make_padded_circle(body_b, radius=5, length=5, plane_label="XY_Plane")
    top = find_face(pad, normal=(0, 0, 1), center=(0, 0, 15), tol=0.5)
    assert top, "could not locate the pad top face"

    body_a = doc.addObject("PartDesign::Body", "DatumBody")
    datum = body_a.newObject("PartDesign::Plane", "CrossDatum")
    datum.AttachmentSupport = [(pad, top)]
    datum.MapMode = "FlatFace"
    datum.AttachmentOffset = FreeCAD.Placement()
    doc.recompute()

    resp = preview_attachment_operation(freecad_session, True, doc.Name, datum.Name)
    payload = _payload(resp)

    assert payload["ok"] is True
    assert payload["datum"] == datum.Name
    assert payload["datum_body"] == body_a.Name
    assert payload["support_body"] == body_b.Name
    # The risk condition: support in a different body with a non-identity placement.
    assert payload["source_body_placement_dropped"] is True
    # A structured diff is always surfaced.
    assert "diff" in payload and "signed_distance_mm" in payload["diff"]
    assert "angle_deg" in payload["diff"]
