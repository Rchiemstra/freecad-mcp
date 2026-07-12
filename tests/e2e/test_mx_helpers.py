"""M6 / M3 / I10 e2e: face_normal, placement_audit, and the capture/diff
round-trip, against a live FreeCAD.
"""
from __future__ import annotations

import json

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")
Sketcher = pytest.importorskip("Sketcher")

from freecad_mcp.operations.diagnostics import (  # noqa: E402
    capture_state_operation,
    face_normal_operation,
    geometric_diff_operation,
    placement_audit_operation,
)
from tests.e2e._helpers import find_face, make_padded_circle, tool_response_text  # noqa: E402

pytestmark = pytest.mark.e2e


def _payload(response) -> dict:
    text = tool_response_text(response)
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


def _approx(vec, target, tol=1e-2):
    return all(abs(float(vec[k]) - float(target[i])) <= tol for i, k in enumerate("xyz"))


def test_face_normal_returns_global_top_normal(freecad_session):
    doc = freecad_session.doc
    body = doc.addObject("PartDesign::Body", "Body")
    _, pad = make_padded_circle(body, radius=3, length=4, plane_label="XY_Plane")
    top = find_face(pad, normal=(0, 0, 1), center=(0, 0, 4), tol=0.5)
    assert top, "could not locate the pad top face"

    resp = face_normal_operation(freecad_session, True, doc.Name, pad.Name, top)
    payload = _payload(resp)
    assert payload["ok"] is True
    assert payload["subshape"] == top
    assert _approx(payload["global_normal"], (0, 0, 1))
    assert _approx(payload["global_center"], (0, 0, 4), tol=1e-2)


def test_placement_audit_lists_body_placement(freecad_session):
    doc = freecad_session.doc
    body = doc.addObject("PartDesign::Body", "MovedBody")
    body.Placement.Base = FreeCAD.Vector(1, 2, 3)
    FreeCAD.ActiveDocument.recompute()

    resp = placement_audit_operation(freecad_session, True, doc.Name)
    payload = _payload(resp)
    assert payload["ok"] is True
    names = {b["name"] for b in payload["bodies"]}
    assert body.Name in names
    row = next(b for b in payload["bodies"] if b["name"] == body.Name)
    assert _approx(row["placement_base"], (1, 2, 3))
    assert _approx(row["global_placement_base"], (1, 2, 3))


def test_capture_state_and_geometric_diff_round_trip(freecad_session):
    doc = freecad_session.doc
    body = doc.addObject("PartDesign::Body", "Body")
    _, pad = make_padded_circle(body, radius=2, length=1, plane_label="XY_Plane")

    before = _payload(capture_state_operation(
        freecad_session, True, doc.Name, [pad.Name],
    ))

    # Mutate: lengthen the pad so its bbox changes.
    pad.Length = 3
    FreeCAD.ActiveDocument.recompute()

    diff = _payload(geometric_diff_operation(
        freecad_session, True, doc.Name, before, [pad.Name],
    ))
    assert diff["ok"] is True
    row = next(d for d in diff["diffs"] if d["name"] == pad.Name)
    assert row["changed"] is True
    assert row["bbox_after"]["zmax"] > row["bbox_before"]["zmax"]
