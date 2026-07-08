"""I7 e2e: snapshot then mutate then restore round-trips a live FreeCAD document
(P12) — a bad step is one restore call away.

Snapshot a doc with a padded circle, add an extra object, restore, and assert
the extra object is gone while the original pad survives.
"""
from __future__ import annotations

import json

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")
Sketcher = pytest.importorskip("Sketcher")

from freecad_mcp.operations.snapshot import (  # noqa: E402
    restore_operation,
    snapshot_operation,
)
from tests.e2e._helpers import make_padded_circle  # noqa: E402

pytestmark = pytest.mark.e2e


def _payload(response) -> dict:
    text = "".join(item.text for item in response if hasattr(item, "text"))
    if "Output:" in text:
        text = text.split("Output:", 1)[1].strip()
    # Recompute progress noise can surround the payload line, so scan from the
    # end for the first line that parses as JSON instead of trusting a fixed
    # line position.
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise AssertionError(f"no JSON payload line in response text: {text!r}")


def test_snapshot_restore_round_trip(freecad_session):
    doc = freecad_session.doc
    doc_name = doc.Name
    body = doc.addObject("PartDesign::Body", "Body")
    _, pad = make_padded_circle(body, radius=3, length=2, plane_label="XY_Plane")
    pad_name = pad.Name

    snap = snapshot_operation(freecad_session, True, doc_name)
    snap_payload = _payload(snap)
    assert snap_payload["ok"] is True
    snap_id = snap_payload["snapshot_id"]

    # Mutate: add an extra object that was NOT in the snapshot.
    extra = doc.addObject("Part::Box", "ExtraBox")
    FreeCAD.ActiveDocument.recompute()
    assert extra.Name in {o.Name for o in FreeCAD.getDocument(doc_name).Objects}

    restored = restore_operation(freecad_session, True, doc_name, snap_id)
    restored_payload = _payload(restored)
    assert restored_payload["ok"] is True
    assert restored_payload["restored_id"] == snap_id
    # Restore-in-place contract: the reopened document keeps the original name
    # (the snapshot file is saved as <DocName>.FCStd for exactly this reason).
    assert restored_payload["new_doc"] == doc_name

    names = {o.Name for o in FreeCAD.getDocument(doc_name).Objects}
    assert "ExtraBox" not in names, "restore did not drop the post-snapshot mutation"
    assert pad_name in names, "restore lost the original pad"
