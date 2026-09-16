"""E2E: parametric Spreadsheet → expression → native Pad / Pocket.

These tests run under FreeCADCmd. The mutation-lane regression requires the
branch-built native collaboration API rather than stock FreeCAD.
"""
from __future__ import annotations

import json
import math

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")
Sketcher = pytest.importorskip("Sketcher")

from freecad_mcp.operations.parametric import (  # noqa: E402
    body_create_operation,
    body_set_tip_operation,
    diagnose_parametric_operation,
    set_expression_operation,
    sketch_attach_operation,
    sketch_edit_constraint_operation,
    spreadsheet_create_operation,
    spreadsheet_list_aliases_operation,
    spreadsheet_set_cells_operation,
)
from freecad_mcp.operations.core import (  # noqa: E402
    pad_feature_operation,
    pocket_feature_operation,
    redo_operation,
    sketch_add_circle_operation,
    sketch_add_constraint_operation,
    sketch_add_geometry_operation,
    sketch_create_operation,
    undo_operation,
)
from tests.e2e._helpers import (  # noqa: E402
    add_xy_sketch,
    make_padded_circle,
    tool_response_text,
)

pytestmark = [pytest.mark.e2e]


def _json_from_response(resp) -> dict:
    text = tool_response_text(resp)
    if "Output:" in text:
        text = text.split("Output:", 1)[1].strip()
    # Prefer the last JSON object in the payload (stdout may include extras).
    decoder = json.JSONDecoder()
    objs = []
    idx = 0
    while idx < len(text):
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text):
            break
        try:
            obj, end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            idx += 1
            continue
        if isinstance(obj, dict):
            objs.append(obj)
        idx = end
    assert objs, f"no JSON object in response: {text!r}"
    return objs[-1]


def _assert_mutation_ready(conn, doc_name: str) -> dict:
    readiness = conn.get_mutation_readiness(doc_name)
    assert readiness.get("success") is True, readiness
    assert readiness.get("ready") is True, readiness
    assert readiness.get("reasons") == [], readiness
    documents = readiness.get("documents") or []
    assert len(documents) == 1, readiness
    item = documents[0]
    assert item.get("document") == doc_name, item
    assert item.get("ready") is True, item
    assert item.get("pending_transaction") is False, item
    assert item.get("booked_transaction_id") == 0, item
    assert item.get("transaction_locked") is False, item
    assert item.get("must_execute") is False, item
    assert item.get("pending_removal") is False, item
    assert item.get("recomputing") is False, item
    assert item.get("collaboration_blocked") is False, item
    assert item.get("collaboration_poisoned") is False, item
    assert item.get("quarantined") is False, item
    return item


def _assert_native_mutation_ready(document) -> None:
    readiness = document.getMutationReadiness()
    assert readiness.get("ready") is True, readiness
    assert readiness.get("stable_event_supported") is True, readiness
    assert readiness.get("pending_transaction") is False, readiness
    assert readiness.get("booked_transaction") == 0, readiness
    assert readiness.get("transaction_locked") is False, readiness
    assert readiness.get("recomputing") is False, readiness
    assert readiness.get("must_execute") is False, readiness
    assert readiness.get("pending_removal") is False, readiness
    assert readiness.get("commit_barrier") is False, readiness
    assert readiness.get("notification_replay") is False, readiness
    assert readiness.get("poisoned") is False, readiness
    assert readiness.get("quarantined") is False, readiness


def _successful(result: dict) -> bool:
    return (
        isinstance(result, dict)
        and result.get("success") is True
        and result.get("ok") is not False
    )


def test_native_create_sequences_leave_mutation_lane_ready(freecad_session):
    """Body→Sketch and Sheet→cells commit without stranded recompute work."""

    conn = freecad_session
    doc_name = conn.doc.Name

    body = body_create_operation(conn, True, doc_name, "Body")
    assert not body.isError, tool_response_text(body)
    _assert_mutation_ready(conn, doc_name)

    sketch = sketch_create_operation(
        conn,
        True,
        doc_name,
        "Sketch",
        body_name="Body",
        attach_to="XY_Plane",
    )
    assert not sketch.isError, tool_response_text(sketch)
    _assert_mutation_ready(conn, doc_name)

    sheet = spreadsheet_create_operation(conn, True, doc_name, "Dims")
    assert not sheet.isError, tool_response_text(sheet)
    _assert_mutation_ready(conn, doc_name)

    cells = spreadsheet_set_cells_operation(
        conn,
        True,
        doc_name,
        "Dims",
        [
            {"address": "A1", "value": 3.0},
            {"address": "B1", "value": "120 mm"},
        ],
    )
    assert not cells.isError, tool_response_text(cells)
    _assert_mutation_ready(conn, doc_name)
    _assert_native_mutation_ready(conn.doc)


def test_sketch_create_attaches_xz_plane_and_offset_atomically(freecad_session):
    """Origin support and offset are applied while the sketch is still new."""

    conn = freecad_session
    doc_name = conn.doc.Name
    assert not body_create_operation(conn, True, doc_name, "Body").isError
    offset = {
        "Base": {"x": 0.0, "y": 0.0, "z": 25.0},
        "Rotation": {
            "Axis": {"x": 0.0, "y": 0.0, "z": 1.0},
            "Angle": 15.0,
        },
    }

    result = sketch_create_operation(
        conn,
        True,
        doc_name,
        "SketchXZ",
        body_name="Body",
        attach_to="XZ_Plane",
        attachment_offset=offset,
    )

    assert not result.isError, tool_response_text(result)
    sketch = conn.doc.getObject("SketchXZ")
    assert sketch is not None
    assert sketch.MapMode == "FlatFace"
    support = list(sketch.AttachmentSupport)
    assert len(support) == 1
    assert support[0][0].Name == "XZ_Plane"
    assert math.isclose(sketch.AttachmentOffset.Base.z, 25.0, abs_tol=1e-8)
    assert math.isclose(
        math.degrees(sketch.AttachmentOffset.Rotation.Angle),
        15.0,
        abs_tol=1e-8,
    )
    conn.doc.recompute()
    assert sketch.MapMode == "FlatFace"
    assert support[0][0].Name == "XZ_Plane"
    _assert_mutation_ready(conn, doc_name)
    _assert_native_mutation_ready(conn.doc)


def test_native_mutation_lane_recovers_after_open_profile_failure(freecad_session):
    """A failed Pad must not poison later features, history, or another doc."""

    conn = freecad_session
    doc = conn.doc
    doc_name = doc.Name
    # ``freecad_session`` capability-gates the whole production mutation facade:
    # branch CI fails closed when native collaboration is required, while the
    # stock conda compatibility image reports an explicit skip.
    assert callable(getattr(doc, "commitCompatibilityMutation", None))
    assert callable(getattr(doc, "getMutationReadiness", None))
    doc.UndoMode = 1

    assert not body_create_operation(conn, True, doc_name, "Body").isError
    assert not sketch_create_operation(
        conn,
        True,
        doc_name,
        "Outer",
        body_name="Body",
        attach_to="XY_Plane",
    ).isError
    assert not sketch_add_geometry_operation(
        conn,
        True,
        doc_name,
        "Outer",
        [
            {
                "type": "line",
                "start": {"x": -6.0, "y": -4.0},
                "end": {"x": 6.0, "y": -4.0},
            }
        ],
    ).isError

    history_before_bad_pad = int(doc.UndoCount)
    rejected = conn.pad_feature(
        doc_name,
        "Outer",
        "RejectedPad",
        4.0,
        "Body",
        False,
        False,
        True,
    )
    assert rejected.get("success") is False, rejected
    assert rejected.get("ok") is False, rejected
    assert rejected.get("error") == "Sketch profile is not pad-ready", rejected
    assert rejected.get("diagnostics", {}).get("is_closed") is not True, rejected
    assert doc.getObject("RejectedPad") is None
    assert int(doc.UndoCount) == history_before_bad_pad
    _assert_mutation_ready(conn, doc_name)
    _assert_native_mutation_ready(doc)

    # Repair the same sketch into a constrained closed wire. The first edge is
    # retained so this exercises recovery from the exact semantic preflight
    # failure above, not a fresh-sketch retry.
    assert not sketch_add_geometry_operation(
        conn,
        True,
        doc_name,
        "Outer",
        [
            {
                "type": "line",
                "start": {"x": 6.0, "y": -4.0},
                "end": {"x": 6.0, "y": 4.0},
            },
            {
                "type": "line",
                "start": {"x": 6.0, "y": 4.0},
                "end": {"x": -6.0, "y": 4.0},
            },
            {
                "type": "line",
                "start": {"x": -6.0, "y": 4.0},
                "end": {"x": -6.0, "y": -4.0},
            },
        ],
    ).isError
    assert not sketch_add_constraint_operation(
        conn,
        True,
        doc_name,
        "Outer",
        [
            {"type": "Coincident", "geo1": 0, "pos1": 2, "geo2": 1, "pos2": 1},
            {"type": "Coincident", "geo1": 1, "pos1": 2, "geo2": 2, "pos2": 1},
            {"type": "Coincident", "geo1": 2, "pos1": 2, "geo2": 3, "pos2": 1},
            {"type": "Coincident", "geo1": 3, "pos1": 2, "geo2": 0, "pos2": 1},
            {"type": "Horizontal", "geo": 0},
            {"type": "Vertical", "geo": 1},
            {"type": "Horizontal", "geo": 2},
            {"type": "Vertical", "geo": 3},
        ],
    ).isError
    assert doc.getObject("Outer").Shape.isClosed()

    pad_history_before = int(doc.UndoCount)
    pad = conn.pad_feature(
        doc_name, "Outer", "Pad", 4.0, "Body", False, False, True
    )
    assert _successful(pad), pad
    assert pad.get("feature") == "Pad", pad
    assert int(doc.UndoCount) == pad_history_before + 1
    assert str(doc.UndoNames[0]).startswith("Collaborative operation ")
    _assert_mutation_ready(conn, doc_name)

    assert not sketch_create_operation(
        conn,
        True,
        doc_name,
        "Inner",
        body_name="Body",
        attach_to="XY_Plane",
    ).isError
    assert not sketch_add_circle_operation(
        conn, True, doc_name, "Inner", 0.0, 0.0, 2.0
    ).isError
    pocket_history_before = int(doc.UndoCount)
    pocket = conn.pocket_feature(
        doc_name, "Inner", "Pocket", 4.0, "Body", False, True, True
    )
    assert _successful(pocket), pocket
    assert pocket.get("feature") == "Pocket", pocket
    assert int(doc.UndoCount) == pocket_history_before + 1
    pocket_volume = float(doc.getObject("Pocket").Shape.Volume)
    assert pocket_volume < float(doc.getObject("Pad").Shape.Volume)
    _assert_mutation_ready(conn, doc_name)

    undone = undo_operation(conn, doc_name)
    assert not undone.isError, tool_response_text(undone)
    assert doc.getObject("Pocket") is None
    restored_pad = doc.getObject("Pad")
    assert restored_pad is not None
    assert doc.getObject("Body").Tip is restored_pad
    assert int(doc.RedoCount) == 1
    _assert_mutation_ready(conn, doc_name)

    redone = redo_operation(conn, doc_name)
    assert not redone.isError, tool_response_text(redone)
    restored_pocket = doc.getObject("Pocket")
    assert restored_pocket is not None
    assert doc.getObject("Body").Tip is restored_pocket
    assert float(restored_pocket.Shape.Volume) == pytest.approx(pocket_volume)
    assert int(doc.RedoCount) == 0
    _assert_mutation_ready(conn, doc_name)
    _assert_native_mutation_ready(doc)

    second_name = f"{doc_name}_Second"
    second = FreeCAD.newDocument(second_name)
    second.UndoMode = 1
    try:
        _assert_mutation_ready(conn, second_name)
        assert not body_create_operation(conn, True, second_name, "Body").isError
        assert not sketch_create_operation(
            conn,
            True,
            second_name,
            "Outer",
            body_name="Body",
            attach_to="XY_Plane",
        ).isError
        assert not sketch_add_circle_operation(
            conn, True, second_name, "Outer", 0.0, 0.0, 3.0
        ).isError
        second_pad = conn.pad_feature(
            second_name, "Outer", "Pad", 2.0, "Body", False, False, True
        )
        assert _successful(second_pad), second_pad
        _assert_mutation_ready(conn, second_name)
        _assert_native_mutation_ready(second)
        _assert_mutation_ready(conn, doc_name)
    finally:
        FreeCAD.closeDocument(second_name)


def test_alias_radius_pad_volume_updates(freecad_session):
    """Sheet alias → circle radius expression → pad → change alias → volume changes."""
    conn = freecad_session
    doc = conn.doc.Name

    assert not spreadsheet_create_operation(conn, True, doc, "Dims").isError
    assert not spreadsheet_set_cells_operation(
        conn,
        True,
        doc,
        "Dims",
        [
            {"address": "A1", "value": 2.0, "alias": "Bore"},
            {"address": "A2", "value": 5.0, "alias": "Depth"},
        ],
    ).isError
    aliases = _json_from_response(spreadsheet_list_aliases_operation(conn, True, doc, "Dims"))
    assert aliases.get("aliases", {}).get("Bore") == "A1"

    assert not body_create_operation(conn, True, doc, "Body").isError
    assert not sketch_create_operation(
        conn, True, doc, "Sketch", body_name="Body", attach_to="XY_Plane"
    ).isError
    assert not sketch_add_circle_operation(conn, True, doc, "Sketch", 0, 0, 2.0).isError
    assert not sketch_add_constraint_operation(
        conn,
        True,
        doc,
        "Sketch",
        [{"type": "Radius", "geo": 0, "value": 2.0, "name": "BoreR"}],
    ).isError

    # Bind radius + pad length to spreadsheet aliases
    sk = conn.doc.getObject("Sketch")
    radius_idx = None
    for i, c in enumerate(sk.Constraints):
        if getattr(c, "Name", "") == "BoreR":
            radius_idx = i
            break
    assert radius_idx is not None, "named BoreR constraint missing"
    assert not set_expression_operation(
        conn, True, doc, "Sketch", f"Constraints[{radius_idx}]", "<<Dims>>.Bore"
    ).isError
    assert not pad_feature_operation(
        conn, True, doc, "Sketch", "Pad", 5.0, body_name="Body"
    ).isError
    assert not set_expression_operation(
        conn, True, doc, "Pad", "Length", "<<Dims>>.Depth"
    ).isError
    assert not body_set_tip_operation(conn, True, doc, "Body", "Pad").isError

    conn.doc.recompute()
    pad = conn.doc.getObject("Pad")
    vol1 = float(pad.Shape.Volume)
    expected1 = math.pi * (2.0**2) * 5.0
    assert abs(vol1 - expected1) / expected1 < 0.05, f"vol1={vol1} expected~{expected1}"

    # Mutate aliases — geometry must update without rewriting sketch
    sheet = conn.doc.getObject("Dims")
    sheet.set("A1", "3.0")
    sheet.set("A2", "8.0")
    conn.doc.recompute()
    vol2 = float(conn.doc.getObject("Pad").Shape.Volume)
    expected2 = math.pi * (3.0**2) * 8.0
    assert abs(vol2 - expected2) / expected2 < 0.05, f"vol2={vol2} expected~{expected2}"
    assert vol2 > vol1 * 1.5


def test_body_xy_pad_pocket(freecad_session):
    conn = freecad_session
    doc = conn.doc.Name
    assert not body_create_operation(conn, True, doc, "Body").isError
    assert not sketch_create_operation(conn, True, doc, "Outer", body_name="Body").isError
    assert not sketch_attach_operation(conn, True, doc, "Outer", "XY_Plane").isError
    assert not sketch_add_circle_operation(conn, True, doc, "Outer", 0, 0, 6.0).isError
    assert not sketch_add_constraint_operation(
        conn, True, doc, "Outer", [{"type": "Radius", "geo": 0, "value": 6.0}]
    ).isError
    assert not pad_feature_operation(
        conn, True, doc, "Outer", "Pad", 4.0, body_name="Body"
    ).isError

    assert not sketch_create_operation(conn, True, doc, "Inner", body_name="Body").isError
    assert not sketch_attach_operation(conn, True, doc, "Inner", "XY_Plane").isError
    assert not sketch_add_circle_operation(conn, True, doc, "Inner", 0, 0, 2.0).isError
    assert not sketch_add_constraint_operation(
        conn, True, doc, "Inner", [{"type": "Radius", "geo": 0, "value": 2.0}]
    ).isError
    # Same-plane pocket often needs Reversed to cut into the pad solid.
    assert not pocket_feature_operation(
        conn, True, doc, "Inner", "Pocket", 4.0, body_name="Body", reversed_dir=True
    ).isError
    assert not body_set_tip_operation(conn, True, doc, "Body", "Pocket").isError
    conn.doc.recompute()
    body = conn.doc.getObject("Body")
    assert body.Tip is not None
    assert body.Tip.Name == "Pocket"
    pad_vol = float(conn.doc.getObject("Pad").Shape.Volume)
    tip_vol = float(body.Tip.Shape.Volume)
    # Pocket must reduce solid vs the preceding pad.
    assert tip_vol < pad_vol * 0.95, f"tip_vol={tip_vol} pad_vol={pad_vol}"
    expected = math.pi * (6.0**2 - 2.0**2) * 4.0
    assert abs(tip_vol - expected) / expected < 0.12, f"tip_vol={tip_vol} expected~{expected}"


def test_zero_material_pocket_is_rejected_and_rolled_back(freecad_session):
    conn = freecad_session
    doc = conn.doc
    doc_name = conn.doc.Name
    body = doc.addObject("PartDesign::Body", "Body")
    _, pad = make_padded_circle(body, radius=6.0, length=4.0)
    away = add_xy_sketch(body, "Away")
    away.addGeometry(
        Part.Circle(
            FreeCAD.Vector(0, 0, 0),
            FreeCAD.Vector(0, 0, 1),
            2.0,
        ),
        False,
    )
    doc.recompute()
    _assert_native_mutation_ready(doc)

    rejected = conn.pocket_feature(
        doc_name,
        "Away",
        "ZeroPocket",
        4.0,
        "Body",
        False,
        False,
        True,
    )

    assert rejected["success"] is False, rejected
    assert rejected["ok"] is False, rejected
    assert rejected["error_code"] == "ZERO_MATERIAL_DELTA", rejected
    assert rejected["material_delta_mm3"] == pytest.approx(0.0), rejected
    assert doc.getObject("ZeroPocket") is None
    assert body.Tip is pad
    pending = conn.get_mutation_readiness(doc_name)
    assert pending["reasons"] == ["pending_recompute", "native_not_ready"], pending
    settled = conn._dispatch("recompute_document", doc_name)
    assert settled["success"] is True, settled
    _assert_mutation_ready(conn, doc_name)


def test_bad_expression_structured_error(freecad_session):
    conn = freecad_session
    doc = conn.doc.Name
    assert not body_create_operation(conn, True, doc, "Body").isError
    assert not sketch_create_operation(
        conn, True, doc, "Sketch", body_name="Body", attach_to="XY_Plane"
    ).isError
    assert not sketch_add_circle_operation(conn, True, doc, "Sketch", 0, 0, 2.0).isError
    assert not pad_feature_operation(
        conn, True, doc, "Sketch", "Pad", 3.0, body_name="Body"
    ).isError

    resp = set_expression_operation(
        conn, True, doc, "Pad", "Length", "<<MissingSheet>>.Nope"
    )
    assert resp.isError, tool_response_text(resp)
    text = tool_response_text(resp)
    assert "expression" in text.lower() or "Failed" in text


def test_named_constraint_edit_after_extra_geometry(freecad_session):
    """Edit by name still works after more geometry is added (index churn)."""
    conn = freecad_session
    doc = conn.doc.Name
    assert not body_create_operation(conn, True, doc, "Body").isError
    assert not sketch_create_operation(
        conn, True, doc, "Sketch", body_name="Body", attach_to="XY_Plane"
    ).isError
    assert not sketch_add_circle_operation(conn, True, doc, "Sketch", 0, 0, 2.0).isError
    assert not sketch_add_constraint_operation(
        conn,
        True,
        doc,
        "Sketch",
        [{"type": "Radius", "geo": 0, "value": 2.0, "name": "MainR"}],
    ).isError
    # Add more geometry so indices after MainR would be fragile if we tracked wrong ones
    assert not sketch_add_circle_operation(conn, True, doc, "Sketch", 10, 0, 1.0).isError
    assert not sketch_add_constraint_operation(
        conn,
        True,
        doc,
        "Sketch",
        [{"type": "Radius", "geo": 1, "value": 1.0, "name": "SideR"}],
    ).isError

    resp = sketch_edit_constraint_operation(
        conn, True, doc, "Sketch", value=4.0, name="MainR"
    )
    assert not resp.isError, tool_response_text(resp)
    payload = _json_from_response(resp)
    assert payload.get("name") == "MainR"
    assert abs(float(payload.get("after", 0)) - 4.0) < 1e-6

    diag = diagnose_parametric_operation(conn, True, doc)
    assert not diag.isError
    d = _json_from_response(diag)
    assert "sketches" in d
    assert "invalid_objects" in d
