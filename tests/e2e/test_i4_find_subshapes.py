"""I4 e2e: find_faces / find_edges locate sub-shapes by geometry against a live
FreeCAD, removing face/edge-index fragility.

A padded circle (radius 5, length 5 on XY) has a planar top face at z=5 with
normal +Z and a circular edge of radius 5 on that top face. The tools must
return those, ranked, with correct global centre / normal / radius.
"""
from __future__ import annotations

import json

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")
Sketcher = pytest.importorskip("Sketcher")

from freecad_mcp.operations.diagnostics import (  # noqa: E402
    find_edges_operation,
    find_faces_operation,
)
from tests.e2e._helpers import make_padded_circle  # noqa: E402

pytestmark = pytest.mark.e2e


def _payload(response) -> dict:
    text = "".join(item.text for item in response if hasattr(item, "text"))
    if "Output:" in text:
        text = text.split("Output:", 1)[1].strip()
    return json.loads(text.splitlines()[-1])


def _approx(vec, target, tol=1e-2):
    return all(abs(float(vec[k]) - float(target[i])) <= tol for i, k in enumerate("xyz"))


def test_find_faces_locates_top_plane_by_normal(freecad_session):
    doc = freecad_session.doc
    body = doc.addObject("PartDesign::Body", "Body")
    _, pad = make_padded_circle(body, radius=5, length=5, plane_label="XY_Plane")

    resp = find_faces_operation(
        freecad_session, True, doc.Name, pad.Name,
        type="Plane",
        normal_approx={"x": 0, "y": 0, "z": 1},
        center_approx={"x": 0, "y": 0, "z": 5},
        center_tol=0.5,
    )
    payload = _payload(resp)
    assert payload["ok"] is True
    assert payload["count"] >= 1
    top = payload["results"][0]
    assert top["type"] == "Plane"
    assert _approx(top["global_normal"], (0, 0, 1))
    assert _approx(top["global_center"], (0, 0, 5), tol=1e-2)


def test_find_edges_locates_top_circle_by_radius(freecad_session):
    doc = freecad_session.doc
    body = doc.addObject("PartDesign::Body", "Body")
    _, pad = make_padded_circle(body, radius=5, length=5, plane_label="XY_Plane")

    resp = find_edges_operation(
        freecad_session, True, doc.Name, pad.Name,
        type="Circle",
        radius=5.0,
        center_approx={"x": 0, "y": 0, "z": 5},
        center_tol=0.5,
    )
    payload = _payload(resp)
    assert payload["ok"] is True
    assert payload["count"] >= 1
    edge = payload["results"][0]
    assert edge["type"] == "Circle"
    assert abs(edge["radius"] - 5.0) <= 1e-3
    assert _approx(edge["global_center"], (0, 0, 5), tol=1e-2)
