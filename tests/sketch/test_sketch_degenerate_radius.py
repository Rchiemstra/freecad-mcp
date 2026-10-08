"""Sketch tools must reject zero, negative and non-finite radii up front.

``sketch_add_circle`` with ``radius=0`` was committed: a degenerate circle that
FreeCAD then reported on every recompute ("Edge too small: Edge1").
"""

from __future__ import annotations

import importlib

import pytest

pytestmark = pytest.mark.unit

_OPS = "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops."
_BASE = {"doc_name": "Doc", "sketch_name": "Sketch"}
_CASES = [
    ("sketch_add_circle", "radius", {"cx": 0, "cy": 0, "radius": 5, "construction": False}),
    ("sketch_add_arc", "radius",
     {"cx": 0, "cy": 0, "radius": 5, "start_angle": 0, "end_angle": 90, "construction": False}),
    ("sketch_add_ellipse", "major_radius",
     {"cx": 0, "cy": 0, "major_radius": 8, "minor_radius": 4, "angle": 0, "construction": False}),
    ("sketch_add_ellipse", "minor_radius",
     {"cx": 0, "cy": 0, "major_radius": 8, "minor_radius": 4, "angle": 0, "construction": False}),
    ("sketch_add_regular_polygon", "radius",
     {"cx": 0, "cy": 0, "radius": 5, "sides": 6, "angle": 0, "construction": False}),
    ("sketch_add_arc_of_ellipse", "major_radius",
     {"cx": 0, "cy": 0, "major_radius": 8, "minor_radius": 4, "start_angle": 0,
      "end_angle": 90, "angle": 0, "construction": False}),
    ("sketch_add_arc_of_ellipse", "minor_radius",
     {"cx": 0, "cy": 0, "major_radius": 8, "minor_radius": 4, "start_angle": 0,
      "end_angle": 90, "angle": 0, "construction": False}),
    ("sketch_fillet", "radius", {"geo1": 0, "geo2": 1, "radius": 2}),
]


def _build(op: str, args: dict[str, object]):
    module = importlib.import_module(_OPS + op)
    return getattr(module, f"build_{op}_request")(**_BASE, **args)


@pytest.mark.parametrize(("op", "field", "args"), _CASES)
def test_valid_radius_builds_a_request(op, field, args):
    assert not isinstance(_build(op, args), dict)


@pytest.mark.parametrize("value", [0, -3, float("nan"), float("inf")])
@pytest.mark.parametrize(("op", "field", "args"), _CASES)
def test_degenerate_radius_is_an_invalid_argument(op, field, args, value):
    failure = _build(op, {**args, field: value})

    assert isinstance(failure, dict)
    assert failure["error_code"] == "INVALID_ARGUMENT"
    assert field in failure["error"]
