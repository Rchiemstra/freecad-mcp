"""P7: a datum plane's origin lands on the plane's nearest-to-global-origin
point, not the support face's centre.

For an infinite plane the *plane* is correct, but the datum's origin (and thus
a sketch built on it) maps (0,0) to the plane's nearest-to-origin point, not
the face centre. This is undocumented and unintuitive; it may be intended
FreeCAD behaviour. This test documents the desired behaviour (origin == face
centre) as a known-issue marker.
"""
from __future__ import annotations

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")

from tests.e2e._helpers import (
    face_global_center,
    find_face,
    make_padded_circle,
    plane_global_base,
)

# First calibrated run against this branch's FreeCAD (1.2.0dev): the bug this
# test reproduces is fixed, so the strict xfail flipped to XPASS and failed the
# run. Keep the test as a plain regression gate against the bug returning.
pytestmark = [
    pytest.mark.core,
]


def test_datum_origin_is_face_centre(freecad_session):
    doc = freecad_session.doc
    # Identity source body so P1 does not confound the origin check.
    body_b = doc.addObject("PartDesign::Body", "Source")
    _, pad = make_padded_circle(body_b, radius=5, length=5, plane_label="XY_Plane")
    top = find_face(pad, normal=(0, 0, 1), center=(0, 0, 5), tol=0.5)
    assert top

    body_a = doc.addObject("PartDesign::Body", "DatumOwner")
    datum = body_a.newObject("PartDesign::Plane", "D")
    datum.AttachmentSupport = [(pad, top)]
    datum.MapMode = "FlatFace"
    datum.AttachmentOffset = FreeCAD.Placement()
    doc.recompute()

    face_c = face_global_center(pad, top)
    origin = plane_global_base(datum)
    err = (origin - face_c).Length
    assert err <= 1e-3, f"datum origin {origin} != face centre {face_c} (err {err:.4e})"
