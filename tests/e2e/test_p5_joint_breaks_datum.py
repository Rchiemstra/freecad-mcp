"""P5: an Assembly joint moving a body breaks cross-body datums on that body.

You can have dynamic follow (Assembly joint) *or* a cross-body datum that
follows, but not both: the moment a joint moves a body to a non-identity
placement, the cross-body datum referencing a face on that body stops tracking
the face's global pose. This is a design-level conflict between the Assembly
and PartDesign workbenches.

Architectural; this test documents the desired (currently failing) behaviour.
Requires the Assembly workbench; skipped if unavailable.
"""
from __future__ import annotations

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")
Sketcher = pytest.importorskip("Sketcher")

from tests.e2e._helpers import (
    distance_point_to_plane,
    face_global_center,
    face_global_normal,
    find_face,
    make_padded_circle,
    plane_global_base,
    plane_global_normal,
)

pytestmark = [
    pytest.mark.core,
    pytest.mark.xfail(
        strict=True,
        reason="FreeCAD: Assembly joint movement breaks cross-body datums on the moved body",
    ),
]


def test_joint_moved_body_still_tracks_cross_body_datum(freecad_session):
    pytest.importorskip("Assembly")  # needs the Assembly workbench
    doc = freecad_session.doc

    # Source body that a joint will move off identity.
    body_b = doc.addObject("PartDesign::Body", "MovableSource")
    _, pad = make_padded_circle(body_b, radius=5, length=5, plane_label="XY_Plane")
    top = find_face(pad, normal=(0, 0, 1), center=(0, 0, 5), tol=0.5)
    assert top, "could not locate the pad top face"

    body_a = doc.addObject("PartDesign::Body", "DatumOwner")
    datum = body_a.newObject("PartDesign::Plane", "CrossDatum")
    datum.AttachmentSupport = [(pad, top)]
    datum.MapMode = "FlatFace"
    datum.AttachmentOffset = FreeCAD.Placement()
    doc.recompute()

    # Move the source body with a non-identity placement (simulating a solved joint).
    body_b.Placement = FreeCAD.Placement(
        FreeCAD.Vector(0, 0, 10), FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 0)
    )
    doc.recompute()

    face_n = face_global_normal(pad, top)
    datum_n = plane_global_normal(datum)
    dot = datum_n.x * face_n.x + datum_n.y * face_n.y + datum_n.z * face_n.z
    assert abs(abs(dot) - 1.0) <= 1e-2, f"datum normal {datum_n} != face normal {face_n} after joint move"
    dist = abs(distance_point_to_plane(face_global_center(pad, top), plane_global_base(datum), datum_n))
    assert dist <= 1e-2, f"datum drifted {dist:.4e} mm from the moved source face"
