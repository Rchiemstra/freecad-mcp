"""E2E: parametric Spreadsheet → expression → Pad / named constraints.

These tests run only inside the freecad-mcp Docker image (FreeCADCmd).
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
    sketch_add_circle_operation,
    sketch_add_constraint_operation,
    sketch_create_operation,
)
from tests.e2e._helpers import tool_response_text  # noqa: E402

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
