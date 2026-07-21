"""E2E: diagnose_pocket / diagnose_helix / compare_documents against live FreeCADCmd."""

from __future__ import annotations

import json

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")
Sketcher = pytest.importorskip("Sketcher")

from freecad_mcp.operations.interactive import (  # noqa: E402
    compare_documents_operation,
    diagnose_helix_operation,
    diagnose_pocket_operation,
)
from tests.e2e._helpers import make_padded_circle, tool_response_text  # noqa: E402

pytestmark = pytest.mark.e2e


def _payload(response) -> dict:
    text = tool_response_text(response)
    if "Output:" in text:
        text = text.split("Output:", 1)[1].strip()
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    # Some tools return bare JSON as the whole text content.
    try:
        return json.loads(text)
    except Exception as exc:
        raise AssertionError(f"no JSON payload in response text: {text!r}") from exc


def _make_pocket(doc, body):
    _, pad = make_padded_circle(
        body, radius=5.0, length=4.0, sketch_name="PadSketch", pad_name="Pad"
    )
    # Pocket profile coplanar with the pad sketch plane (same body), then reverse.
    sk = body.newObject("Sketcher::SketchObject", "PocketSketch")
    plane = None
    for feat in getattr(body.Origin, "OriginFeatures", []) or []:
        if feat.Label == "XY_Plane" or feat.Name.endswith("XY_Plane"):
            plane = feat
            break
    if plane is not None:
        sk.AttachmentSupport = [(plane, "")]
        sk.MapMode = "FlatFace"
    sk.addGeometry(
        Part.Circle(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 1.5), False
    )
    FreeCAD.ActiveDocument.recompute()
    pocket = body.newObject("PartDesign::Pocket", "TestPocket")
    pocket.Profile = sk
    pocket.Length = 2.0
    if "Reversed" in getattr(pocket, "PropertiesList", []):
        pocket.Reversed = True
    FreeCAD.ActiveDocument.recompute()
    return pocket


def test_diagnose_pocket_reports_reversed_direction_length(freecad_session):
    doc = freecad_session.doc
    body = doc.addObject("PartDesign::Body", "Body")
    pocket = _make_pocket(doc, body)

    payload = _payload(
        diagnose_pocket_operation(freecad_session, True, doc.Name, pocket.Name)
    )
    assert payload["ok"] is True
    assert payload["pocket"] == pocket.Name
    assert payload["type_id"] == "PartDesign::Pocket"
    assert "reversed" in payload and isinstance(payload["reversed"], bool)
    assert float(payload["length"]) == pytest.approx(2.0)
    assert isinstance(payload.get("direction"), dict)
    assert "shape_null" in payload
    assert payload.get("profile") is not None
    # Geometry may be null if OCCT refuses the pocket; still require diagnostics.
    if not payload["shape_null"]:
        assert isinstance(payload.get("volume"), (int, float))
        assert payload.get("bbox") is not None
        assert "face_count" in payload



def test_diagnose_helix_reports_pitch_height_handedness(freecad_session):
    doc = freecad_session.doc
    body = doc.addObject("PartDesign::Body", "Body")
    make_padded_circle(body, radius=3.0, length=1.0)

    # PartDesign AdditiveHelix if available; otherwise create a Helix path object
    # and still diagnose property surface.
    helix = None
    try:
        helix = body.newObject("PartDesign::AdditiveHelix", "TestHelix")
        helix.Pitch = 2.0
        helix.Height = 6.0
        if hasattr(helix, "Radius"):
            helix.Radius = 4.0
        if hasattr(helix, "LeftHanded"):
            helix.LeftHanded = True
        FreeCAD.ActiveDocument.recompute()
    except Exception:
        pytest.skip("PartDesign::AdditiveHelix not available in this FreeCAD build")

    payload = _payload(
        diagnose_helix_operation(freecad_session, True, doc.Name, helix.Name)
    )
    assert payload["ok"] is True
    assert payload["helix"] == helix.Name
    assert "AdditiveHelix" in payload["type_id"] or "Helix" in payload["type_id"]
    if payload.get("pitch") is not None:
        assert float(payload["pitch"]) == pytest.approx(2.0)
    if payload.get("height") is not None:
        assert float(payload["height"]) == pytest.approx(6.0)
    if payload.get("left_handed") is not None:
        assert payload["left_handed"] is True


def test_compare_documents_detects_bbox_change(freecad_session):
    """Compare pads across two open documents via paired capture_state."""
    doc_a = freecad_session.doc
    body_a = doc_a.addObject("PartDesign::Body", "Body")
    _, pad_a = make_padded_circle(
        body_a, radius=2.0, length=1.0, sketch_name="SkA", pad_name="PadA"
    )

    doc_b = FreeCAD.newDocument(doc_a.Name + "_B")
    try:
        body_b = doc_b.addObject("PartDesign::Body", "Body")
        FreeCAD.setActiveDocument(doc_b.Name)
        _, pad_b = make_padded_circle(
            body_b, radius=3.0, length=2.0, sketch_name="SkB", pad_name="PadB"
        )
        FreeCAD.setActiveDocument(doc_a.Name)

        resp = compare_documents_operation(
            freecad_session,
            True,
            doc_a.Name,
            doc_b.Name,
            object_pairs=[{"a": pad_a.Name, "b": pad_b.Name}],
        )
        payload = _payload(resp)
        assert payload["ok"] is True
        assert payload["doc_a"] == doc_a.Name
        assert payload["doc_b"] == doc_b.Name
        assert payload["diff"]["diffs"], "expected at least one diff entry"
        assert any(d.get("changed") for d in payload["diff"]["diffs"])
    finally:
        FreeCAD.closeDocument(doc_b.Name)
        FreeCAD.setActiveDocument(doc_a.Name)
