"""P1: cross-body datum attachment drops the source body's placement.

A `PartDesign::Plane` datum in Body A attached (FlatFace) to a face of a
feature in Body B must land at the face's *global* pose. When Body B has a
non-identity placement, FreeCAD's attacher historically kept the feature's
own placement but dropped the source body's container placement, so the datum
landed at the feature-local pose (a z drop + a compounded normal error).

Refs: FreeCAD #21942 / #22615; upstream fixes #25887, #26298, #30442.
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

pytestmark = pytest.mark.core


def test_cross_body_datum_keeps_source_body_placement(freecad_session):
    doc = freecad_session.doc

    # Body B with a non-identity placement (the source whose placement gets dropped).
    body_b = doc.addObject("PartDesign::Body", "SourceBody")
    body_b.Placement.Base = FreeCAD.Vector(0, 0, 10)
    _, pad = make_padded_circle(body_b, radius=5, length=5, plane_label="XY_Plane")
    # Top face: global normal +Z, global centre z = 10 (body) + 5 (pad) = 15.
    top = find_face(pad, normal=(0, 0, 1), center=(0, 0, 15), tol=0.5)
    assert top, "could not locate the pad top face by geometry"

    # Body A (identity) owns the datum.
    body_a = doc.addObject("PartDesign::Body", "DatumBody")
    datum = body_a.newObject("PartDesign::Plane", "CrossDatum")
    datum.AttachmentSupport = [(pad, top)]
    datum.MapMode = "FlatFace"
    datum.AttachmentOffset = FreeCAD.Placement()
    doc.recompute()

    face_n = face_global_normal(pad, top)
    datum_n = plane_global_normal(datum)
    # Normal must match (within 1e-2 rad) ...
    dot = datum_n.x * face_n.x + datum_n.y * face_n.y + datum_n.z * face_n.z
    assert abs(abs(dot) - 1.0) <= 1e-2, (
        f"datum normal {datum_n} != face normal {face_n} (|cos|={abs(dot):.4f})"
    )
    # ... and the datum plane must contain the face's global centre (distance 0).
    dist = abs(distance_point_to_plane(face_global_center(pad, top), plane_global_base(datum), datum_n))
    assert dist <= 1e-2, f"datum plane misses the source face by {dist:.4e} mm (placement dropped)"
