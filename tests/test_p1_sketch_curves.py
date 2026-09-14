"""
Tests for P1 sketch curve operations.

Layer-A: typed RPC propagation
Layer-B: request routing
Layer-C: Analytic curve math (parametric curve and ellipse)
"""
from __future__ import annotations

import math
from unittest.mock import MagicMock

from mcp.types import TextContent

from freecad_mcp.operations.p1_curves import (
    sketch_add_arc_of_ellipse_operation,
    sketch_add_bezier_operation,
    sketch_add_bspline_operation,
    sketch_add_bspline_through_points_operation,
    sketch_add_ellipse_operation,
    sketch_add_parametric_curve_operation,
    sketch_add_polyline_operation,
    sketch_add_regular_polygon_operation,
    sketch_add_slot_operation,
    sketch_import_points_operation,
    sketch_toggle_construction_operation,
)
from tests.helpers.curves import assert_on_involute_direct


def _typed_success(**extra):
    payload = {
        "contract_version": 1,
        "success": True,
        "ok": True,
        "outcome": "committed",
        "committed": True,
        "retry_safe": False,
        "sketch": "Sk",
        "geometry_indices": [0],
    }
    payload.update(extra)
    return payload


def _typed_failure():
    return {
        "contract_version": 1,
        "success": False,
        "ok": False,
        "outcome": "rejected",
        "committed": False,
        "retry_safe": False,
        "error_code": "oops",
        "error": "oops",
    }


def _ok_conn(method: str):
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    getattr(conn, method).return_value = _typed_success()
    return conn


def _fail_conn(method: str):
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    getattr(conn, method).return_value = _typed_failure()
    return conn


def _text(response) -> str:
    content = response.content if hasattr(response, "content") else response
    return " ".join(item.text for item in content if isinstance(item, TextContent))


class TestSketchAddPolyline:
    _pts = [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}]

    def test_success(self):
        resp = sketch_add_polyline_operation(_ok_conn("sketch_add_polyline"), True, "Doc", "Sk", self._pts)
        assert _text(resp)

    def test_failure(self):
        resp = sketch_add_polyline_operation(_fail_conn("sketch_add_polyline"), True, "Doc", "Sk", self._pts)
        assert "oops" in _text(resp) or "Failed" in _text(resp)

    def test_too_few_points_returns_error(self):
        resp = sketch_add_polyline_operation(_ok_conn("sketch_add_polyline"), True, "Doc", "Sk", [{"x": 0, "y": 0}])
        assert "polyline requires" in _text(resp)

    def test_routes_typed_rpc(self):
        conn = _ok_conn("sketch_add_polyline")
        sketch_add_polyline_operation(conn, True, "Doc", "Sk", self._pts, closed=True, construction=True)
        conn.sketch_add_polyline.assert_called_once_with("Doc", "Sk", self._pts, True, True)


class TestSketchAddBSpline:
    _poles = [{"x": 0, "y": 0}, {"x": 5, "y": 10}, {"x": 10, "y": 0}]

    def test_success(self):
        resp = sketch_add_bspline_operation(_ok_conn("sketch_add_bspline"), True, "Doc", "Sk", self._poles)
        assert _text(resp)

    def test_routes_typed_rpc(self):
        conn = _ok_conn("sketch_add_bspline")
        sketch_add_bspline_operation(
            conn, True, "Doc", "Sk", self._poles,
            knots=[0.0, 0.5, 1.0], multiplicities=[4, 1, 4], degree=2,
        )
        conn.sketch_add_bspline.assert_called_once()


class TestSketchAddBSplineThroughPoints:
    _pts = [{"x": 0, "y": 0}, {"x": 5, "y": 8}, {"x": 10, "y": 0}]

    def test_success(self):
        resp = sketch_add_bspline_through_points_operation(
            _ok_conn("sketch_add_bspline_through_points"), True, "Doc", "Sk", self._pts
        )
        assert _text(resp)

    def test_routes_typed_rpc(self):
        conn = _ok_conn("sketch_add_bspline_through_points")
        sketch_add_bspline_through_points_operation(conn, True, "Doc", "Sk", self._pts, degree=2)
        conn.sketch_add_bspline_through_points.assert_called_once()


class TestSketchAddBezier:
    _poles = [{"x": 0, "y": 0}, {"x": 5, "y": 10}, {"x": 10, "y": 0}]

    def test_success(self):
        resp = sketch_add_bezier_operation(_ok_conn("sketch_add_bezier"), True, "Doc", "Sk", self._poles)
        assert _text(resp)

    def test_routes_typed_rpc(self):
        conn = _ok_conn("sketch_add_bezier")
        sketch_add_bezier_operation(conn, True, "Doc", "Sk", self._poles)
        conn.sketch_add_bezier.assert_called_once()


class TestSketchAddEllipse:
    def test_success(self):
        resp = sketch_add_ellipse_operation(_ok_conn("sketch_add_ellipse"), True, "Doc", "Sk", 0, 0, 10, 5)
        assert _text(resp)

    def test_routes_typed_rpc(self):
        conn = _ok_conn("sketch_add_ellipse")
        sketch_add_ellipse_operation(conn, True, "Doc", "Sk", 2.0, 3.0, 10, 5)
        conn.sketch_add_ellipse.assert_called_once_with("Doc", "Sk", 2.0, 3.0, 10, 5, 0.0, False)


class TestSketchAddArcOfEllipse:
    def test_success(self):
        resp = sketch_add_arc_of_ellipse_operation(
            _ok_conn("sketch_add_arc_of_ellipse"), True, "Doc", "Sk", 0, 0, 10, 5, 0, 180
        )
        assert _text(resp)

    def test_routes_typed_rpc(self):
        conn = _ok_conn("sketch_add_arc_of_ellipse")
        sketch_add_arc_of_ellipse_operation(conn, True, "Doc", "Sk", 0, 0, 10, 5, 0, 180)
        conn.sketch_add_arc_of_ellipse.assert_called_once()


class TestSketchAddSlot:
    def test_success(self):
        resp = sketch_add_slot_operation(_ok_conn("sketch_add_slot"), True, "Doc", "Sk", 0, 0, 20, 0, 4.0)
        assert _text(resp)

    def test_routes_typed_rpc(self):
        conn = _ok_conn("sketch_add_slot")
        sketch_add_slot_operation(conn, True, "Doc", "Sk", 0, 0, 20, 0, 6.0)
        conn.sketch_add_slot.assert_called_once()


class TestSketchAddRegularPolygon:
    def test_success(self):
        resp = sketch_add_regular_polygon_operation(_ok_conn("sketch_add_regular_polygon"), True, "Doc", "Sk", 0, 0, 10, 6)
        assert _text(resp)

    def test_too_few_sides_returns_error(self):
        resp = sketch_add_regular_polygon_operation(_ok_conn("sketch_add_regular_polygon"), True, "Doc", "Sk", 0, 0, 10, 2)
        assert "sides" in _text(resp)

    def test_routes_typed_rpc(self):
        conn = _ok_conn("sketch_add_regular_polygon")
        sketch_add_regular_polygon_operation(conn, True, "Doc", "Sk", 0, 0, 10, 5)
        conn.sketch_add_regular_polygon.assert_called_once()


class TestSketchAddParametricCurve:
    def test_success(self):
        resp = sketch_add_parametric_curve_operation(
            _ok_conn("sketch_add_parametric_curve"), True, "Doc", "Sk",
            "10*math.cos(t)", "10*math.sin(t)", 0, 2 * math.pi
        )
        assert _text(resp)

    def test_samples_too_low_returns_error(self):
        resp = sketch_add_parametric_curve_operation(
            _ok_conn("sketch_add_parametric_curve"), True, "Doc", "Sk", "t", "t", 0, 1, samples=5
        )
        assert "samples must be" in _text(resp)

    def test_t_start_ge_t_end_returns_error(self):
        resp = sketch_add_parametric_curve_operation(
            _ok_conn("sketch_add_parametric_curve"), True, "Doc", "Sk", "t", "t", 1.0, 0.5
        )
        assert "t_start" in _text(resp)

    def test_routes_typed_rpc(self):
        conn = _ok_conn("sketch_add_parametric_curve")
        sketch_add_parametric_curve_operation(conn, True, "Doc", "Sk", "t", "t", 0, 1, samples=20)
        conn.sketch_add_parametric_curve.assert_called_once()

    def test_involute_expressions_correct(self):
        r_b = 10.0
        t0, t1, n = 0.0, 1.2, 50
        ts = [t0 + (t1 - t0) * i / n for i in range(n + 1)]
        pts = [
            (r_b * (math.cos(t) + t * math.sin(t)), r_b * (math.sin(t) - t * math.cos(t)))
            for t in ts
        ]
        assert_on_involute_direct(pts, r_b)


class TestSketchImportPoints:
    _pts = [{"x": 0, "y": 0}, {"x": 5, "y": 5}, {"x": 10, "y": 0}]

    def test_success(self):
        resp = sketch_import_points_operation(_ok_conn("sketch_import_points"), True, "Doc", "Sk", self._pts)
        assert _text(resp)

    def test_routes_typed_rpc(self):
        conn = _ok_conn("sketch_import_points")
        sketch_import_points_operation(conn, True, "Doc", "Sk", self._pts)
        conn.sketch_import_points.assert_called_once_with("Doc", "Sk", self._pts, False)


class TestSketchToggleConstruction:
    def test_success(self):
        resp = sketch_toggle_construction_operation(
            _ok_conn("sketch_toggle_construction"), True, "Doc", "Sk", [0, 1, 2]
        )
        assert _text(resp)

    def test_routes_typed_rpc(self):
        conn = _ok_conn("sketch_toggle_construction")
        sketch_toggle_construction_operation(conn, True, "Doc", "Sk", [3, 5], construction=True)
        conn.sketch_toggle_construction.assert_called_once_with("Doc", "Sk", [3, 5], True)
