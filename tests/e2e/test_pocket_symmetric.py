"""E2E: pocket_feature(symmetric=true) must use PartDesign SideType Symmetric."""

from __future__ import annotations

import math

import pytest

from freecad_mcp.operations.parametric import (
    body_create_operation,
    body_set_tip_operation,
    sketch_attach_operation,
)
from freecad_mcp.operations.core import (
    pad_feature_operation,
    sketch_add_circle_operation,
    sketch_add_constraint_operation,
    sketch_create_operation,
)

pytestmark = [pytest.mark.e2e]


def test_pocket_feature_symmetric_uses_midplane_not_two_sides(freecad_session):
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

    pocket = conn.pocket_feature(doc, "Inner", "Pocket", 4.0, "Body", True, False, True)
    assert pocket.get("success") is True, pocket
    assert not body_set_tip_operation(conn, True, doc, "Body", "Pocket").isError
    conn.doc.recompute()

    pocket_obj = conn.doc.getObject("Pocket")
    assert pocket_obj is not None
    assert pocket_obj.SideType == "Symmetric"

    pad_vol = float(conn.doc.getObject("Pad").Shape.Volume)
    tip_vol = float(conn.doc.getObject("Body").Tip.Shape.Volume)
    assert tip_vol < pad_vol * 0.95, f"tip_vol={tip_vol} pad_vol={pad_vol}"
    expected = math.pi * (6.0**2 * 4.0 - 2.0**2 * 2.0)
    assert abs(tip_vol - expected) / expected < 0.12, f"tip_vol={tip_vol} expected~{expected}"
