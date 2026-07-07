"""P6: `doc.removeObject(body)` leaves orphaned, invalid children.

Removing a PartDesign Body removes the container but can leave its owned
features (sketch, pad, ...) in the document with `parent = None` and state
`Invalid`, producing confusing recompute errors later. Expected: owned
children are removed recursively (or removal is refused with a list).

Refs: FreeCAD #26356 / #29034 (adjacent deletion fixes, exact case not proven).
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
        reason="FreeCAD #26356: doc.removeObject(body) orphans owned children",
    ),
]


def test_remove_body_does_not_orphan_children(freecad_session):
    doc = freecad_session.doc
    body = doc.addObject("PartDesign::Body", "Horn")
    sk, pad = make_padded_circle(body, radius=2, length=1, plane_label="XY_Plane")
    child_names = {sk.Name, pad.Name}
    # All children must exist before removal.
    assert {o.Name for o in doc.Objects} >= child_names

    doc.removeObject(body.Name)

    remaining = [o.Name for o in doc.Objects if o.Name in child_names]
    assert remaining == [], f"orphaned children left after body removal: {remaining}"
