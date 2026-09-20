"""D-18: ``find_faces`` / ``find_edges`` must honour their documented geometric filters.

The typed RPC handlers accepted only ``doc_name`` and ``object_name``, so every call using a
filter was rejected with JSON-RPC ``-32602 Invalid params``; and the typed port of the
original ``find_subshapes`` template dropped the type, normal/direction and radius filters and
the ``type`` / ``global_normal`` / ``radius`` result fields. Uses real OCCT shapes.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import (  # noqa: E402
    diagnostics_shape_actions,
    find_edges,
    find_faces,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.diagnostics_shape_actions import (  # noqa: E402
    find_subshapes,
)

pytestmark = pytest.mark.unit

FILTERS = {
    "type": "Plane",
    "normal_approx": {"x": 0, "y": 0, "z": 1},
    "center_approx": {"x": 0, "y": 0, "z": 450},
    "radius": None,
    "tol": 1e-3,
    "center_tol": 1.0,
    "limit": 10,
}


def _document(shape, *, base=(0, 0, 0)):
    placement = FreeCAD.Placement(FreeCAD.Vector(*base), FreeCAD.Rotation())
    obj = SimpleNamespace(Name="Seat", Shape=shape, Placement=placement, getGlobalPlacement=lambda: placement)
    return SimpleNamespace(getObject={"Seat": obj}.get)


def _seat():
    # 420 x 400 x 20 board whose local origin is its centre-bottom; placed at z = 430.
    return _document(Part.makeBox(420, 400, 20, FreeCAD.Vector(-210, -200, 0)), base=(0, 0, 430))


@pytest.mark.parametrize("module", [find_faces, find_edges])
def test_rpc_accepts_every_documented_filter(module):
    handler = getattr(module, f"rpc_{module.__name__.rsplit('.', 1)[1]}")
    inspect.signature(handler).bind(None, "Chair", "Seat", **FILTERS)


def test_top_face_by_type_and_normal():
    payload = find_subshapes(
        _seat(), "Seat", "Faces", type_filter="plane", normal_approx={"x": 0, "y": 0, "z": 1}
    )
    # A box has exactly two faces whose normal is parallel to Z: top and bottom.
    assert payload["count"] == 2
    assert {round(row["global_center"]["z"], 6) for row in payload["results"]} == {430.0, 450.0}
    assert all(row["type"] == "Plane" for row in payload["results"])
    assert all(abs(abs(row["global_normal"]["z"]) - 1.0) < 1e-9 for row in payload["results"])


def test_center_ranks_the_top_face_first():
    payload = find_subshapes(
        _seat(), "Seat", "Faces", type_filter="Plane",
        normal_approx={"x": 0, "y": 0, "z": 1}, center_approx={"x": 0, "y": 0, "z": 450},
    )
    assert payload["count"] == 1
    assert payload["results"][0]["global_center"] == {"x": 0.0, "y": 0.0, "z": 450.0}


def test_radius_and_type_select_the_cylinder():
    hole = Part.makeBox(40, 40, 40).cut(Part.makeCylinder(2, 40, FreeCAD.Vector(20, 20, 0)))
    payload = find_subshapes(_document(hole), "Seat", "Faces", type_filter="cylinder", radius=2.0)
    assert payload["count"] == 1
    assert payload["results"][0]["type"] == "Cylinder"
    assert payload["results"][0]["radius"] == 2.0


def test_vertical_edges_by_line_direction():
    payload = find_subshapes(
        _seat(), "Seat", "Edges", type_filter="line", normal_approx={"x": 0, "y": 0, "z": 1}
    )
    assert payload["count"] == 4
    assert all(row["length"] == 20.0 for row in payload["results"])


def test_rpc_forwards_filters_to_find_subshapes(monkeypatch):
    seen = {}

    def capture(document, object_name, kind, **kwargs):
        seen.update(kwargs, kind=kind)
        return {"ok": True, "results": []}

    monkeypatch.setattr(diagnostics_shape_actions, "find_subshapes", capture)
    document = _seat()
    collab = SimpleNamespace(freecad=SimpleNamespace(getDocument=lambda _name: document))
    result = find_faces.run_find_faces(collab, "Chair", "Seat", **FILTERS)
    assert result["success"] is True
    assert seen["kind"] == "Faces"
    assert seen["type_filter"] == "Plane"
    assert seen["normal_approx"] == {"x": 0, "y": 0, "z": 1}
    assert seen["center_approx"] == {"x": 0, "y": 0, "z": 450}
