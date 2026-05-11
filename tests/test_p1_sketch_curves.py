"""
Tests for P1 sketch curve operations.

Layer-A: Schema / error propagation
Layer-B: Code-fragment checks
Layer-C: Analytic curve math (parametric curve and ellipse)
"""
from __future__ import annotations

import math
from unittest.mock import MagicMock

import pytest
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
from tests.helpers.curves import (
    assert_ellipse_conformance,
    assert_involute_conformance,
    assert_on_involute_direct,
    assert_points_on_parametric,
    sample_involute,
    involute_x,
    involute_y,
)
from tests.helpers.geometric import assert_code_compiles, assert_code_contains


def _ok_conn():
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {"success": True, "message": "done", "recompute_errors": []}
    return conn


def _fail_conn():
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {"success": False, "error": "oops"}
    return conn


def _code(conn) -> str:
    return conn.execute_code.call_args[0][0]


def _text(response) -> str:
    return " ".join(item.text for item in response if isinstance(item, TextContent))


# ---------------------------------------------------------------------------
# P1-1  sketch_add_polyline
# ---------------------------------------------------------------------------

class TestSketchAddPolyline:
    _pts = [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}]

    def test_success(self):
        resp = sketch_add_polyline_operation(_ok_conn(), True, "Doc", "Sk", self._pts)
        assert _text(resp)

    def test_failure(self):
        resp = sketch_add_polyline_operation(_fail_conn(), True, "Doc", "Sk", self._pts)
        assert "oops" in _text(resp) or "Failed" in _text(resp)

    def test_too_few_points_returns_error(self):
        resp = sketch_add_polyline_operation(_ok_conn(), True, "Doc", "Sk", [{"x": 0, "y": 0}])
        assert "polyline requires" in _text(resp)

    def test_code_compiles(self):
        conn = _ok_conn()
        sketch_add_polyline_operation(conn, True, "Doc", "Sk", self._pts)
        assert_code_compiles(_code(conn))

    def test_code_has_line_segments(self):
        conn = _ok_conn()
        sketch_add_polyline_operation(conn, True, "Doc", "Sk", self._pts)
        assert_code_contains(_code(conn), "LineSegment")

    def test_coordinates_in_code(self):
        conn = _ok_conn()
        sketch_add_polyline_operation(conn, True, "Doc", "Sk", self._pts)
        code = _code(conn)
        assert_code_contains(code, "10", "0")

    def test_closed_polyline_returns_to_start(self):
        conn = _ok_conn()
        sketch_add_polyline_operation(conn, True, "Doc", "Sk", self._pts, closed=True)
        code = _code(conn)
        # Should have 3 segments for 3 points in a closed polyline
        assert code.count("LineSegment") == 3

    def test_construction_flag(self):
        conn = _ok_conn()
        sketch_add_polyline_operation(conn, True, "Doc", "Sk", self._pts, construction=True)
        assert_code_contains(_code(conn), "True")


# ---------------------------------------------------------------------------
# P1-2  sketch_add_bspline
# ---------------------------------------------------------------------------

class TestSketchAddBSpline:
    _poles = [{"x": 0, "y": 0}, {"x": 5, "y": 10}, {"x": 10, "y": 0}]

    def test_success(self):
        resp = sketch_add_bspline_operation(_ok_conn(), True, "Doc", "Sk", self._poles)
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        sketch_add_bspline_operation(conn, True, "Doc", "Sk", self._poles)
        assert_code_compiles(_code(conn))

    def test_bspline_api_called(self):
        conn = _ok_conn()
        sketch_add_bspline_operation(conn, True, "Doc", "Sk", self._poles)
        assert_code_contains(_code(conn), "BSplineCurve", "buildFromPoles")

    def test_knots_path(self):
        conn = _ok_conn()
        sketch_add_bspline_operation(conn, True, "Doc", "Sk", self._poles,
                                     knots=[0.0, 0.5, 1.0], multiplicities=[4, 1, 4])
        assert_code_contains(_code(conn), "buildFromPolesMultsKnots")

    def test_degree_injected(self):
        conn = _ok_conn()
        sketch_add_bspline_operation(conn, True, "Doc", "Sk", self._poles, degree=2)
        assert_code_contains(_code(conn), "2")


# ---------------------------------------------------------------------------
# P1-3  sketch_add_bspline_through_points
# ---------------------------------------------------------------------------

class TestSketchAddBSplineThroughPoints:
    _pts = [{"x": 0, "y": 0}, {"x": 5, "y": 8}, {"x": 10, "y": 0}]

    def test_success(self):
        resp = sketch_add_bspline_through_points_operation(_ok_conn(), True, "Doc", "Sk", self._pts)
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        sketch_add_bspline_through_points_operation(conn, True, "Doc", "Sk", self._pts)
        assert_code_compiles(_code(conn))

    def test_interpolate_called(self):
        conn = _ok_conn()
        sketch_add_bspline_through_points_operation(conn, True, "Doc", "Sk", self._pts)
        assert_code_contains(_code(conn), "interpolate")


# ---------------------------------------------------------------------------
# P1-4  sketch_add_bezier
# ---------------------------------------------------------------------------

class TestSketchAddBezier:
    _poles = [{"x": 0, "y": 0}, {"x": 5, "y": 15}, {"x": 10, "y": 0}]

    def test_success(self):
        resp = sketch_add_bezier_operation(_ok_conn(), True, "Doc", "Sk", self._poles)
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        sketch_add_bezier_operation(conn, True, "Doc", "Sk", self._poles)
        assert_code_compiles(_code(conn))

    def test_bezier_api_called(self):
        conn = _ok_conn()
        sketch_add_bezier_operation(conn, True, "Doc", "Sk", self._poles)
        assert_code_contains(_code(conn), "BezierCurve", "setPoles")


# ---------------------------------------------------------------------------
# P1-5  sketch_add_ellipse
# ---------------------------------------------------------------------------

class TestSketchAddEllipse:
    def test_success(self):
        resp = sketch_add_ellipse_operation(_ok_conn(), True, "Doc", "Sk", 0, 0, 10, 5)
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        sketch_add_ellipse_operation(conn, True, "Doc", "Sk", 0, 0, 10, 5)
        assert_code_compiles(_code(conn))

    def test_ellipse_api_called(self):
        conn = _ok_conn()
        sketch_add_ellipse_operation(conn, True, "Doc", "Sk", 0, 0, 10, 5)
        assert_code_contains(_code(conn), "Part.Ellipse")

    def test_radii_in_code(self):
        conn = _ok_conn()
        sketch_add_ellipse_operation(conn, True, "Doc", "Sk", 2.0, 3.0, 10, 5)
        code = _code(conn)
        assert_code_contains(code, "10", "5")


# ---------------------------------------------------------------------------
# P1-6  sketch_add_arc_of_ellipse
# ---------------------------------------------------------------------------

class TestSketchAddArcOfEllipse:
    def test_success(self):
        resp = sketch_add_arc_of_ellipse_operation(
            _ok_conn(), True, "Doc", "Sk", 0, 0, 10, 5, 0, 180
        )
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        sketch_add_arc_of_ellipse_operation(conn, True, "Doc", "Sk", 0, 0, 10, 5, 0, 180)
        assert_code_compiles(_code(conn))

    def test_arc_of_ellipse_api(self):
        conn = _ok_conn()
        sketch_add_arc_of_ellipse_operation(conn, True, "Doc", "Sk", 0, 0, 10, 5, 0, 180)
        assert_code_contains(_code(conn), "ArcOfEllipse", "Part.Ellipse")


# ---------------------------------------------------------------------------
# P1-7  sketch_add_slot
# ---------------------------------------------------------------------------

class TestSketchAddSlot:
    def test_success(self):
        resp = sketch_add_slot_operation(_ok_conn(), True, "Doc", "Sk", 0, 0, 20, 0, 4.0)
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        sketch_add_slot_operation(conn, True, "Doc", "Sk", 0, 0, 20, 0, 4.0)
        assert_code_compiles(_code(conn))

    def test_has_two_lines_two_arcs(self):
        conn = _ok_conn()
        sketch_add_slot_operation(conn, True, "Doc", "Sk", 0, 0, 20, 0, 4.0)
        code = _code(conn)
        assert code.count("LineSegment") == 2
        assert code.count("ArcOfCircle") == 2

    def test_width_in_code(self):
        conn = _ok_conn()
        sketch_add_slot_operation(conn, True, "Doc", "Sk", 0, 0, 20, 0, 6.0)
        assert_code_contains(_code(conn), "6.0")


# ---------------------------------------------------------------------------
# P1-8  sketch_add_regular_polygon
# ---------------------------------------------------------------------------

class TestSketchAddRegularPolygon:
    def test_success(self):
        resp = sketch_add_regular_polygon_operation(_ok_conn(), True, "Doc", "Sk", 0, 0, 10, 6)
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        sketch_add_regular_polygon_operation(conn, True, "Doc", "Sk", 0, 0, 10, 6)
        assert_code_compiles(_code(conn))

    def test_sides_injected(self):
        conn = _ok_conn()
        sketch_add_regular_polygon_operation(conn, True, "Doc", "Sk", 0, 0, 10, 6)
        assert_code_contains(_code(conn), "6")

    def test_too_few_sides_returns_error(self):
        resp = sketch_add_regular_polygon_operation(_ok_conn(), True, "Doc", "Sk", 0, 0, 10, 2)
        assert "3 sides" in _text(resp)

    def test_line_segments_equal_sides(self):
        conn = _ok_conn()
        sketch_add_regular_polygon_operation(conn, True, "Doc", "Sk", 0, 0, 10, 5)
        # 5-gon should have loop for 5 sides
        assert_code_contains(_code(conn), "range(_n)")


# ---------------------------------------------------------------------------
# P1-9  sketch_add_parametric_curve
# ---------------------------------------------------------------------------

class TestSketchAddParametricCurve:
    def test_success(self):
        resp = sketch_add_parametric_curve_operation(
            _ok_conn(), True, "Doc", "Sk",
            "10*math.cos(t)", "10*math.sin(t)", 0, 2 * math.pi
        )
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        sketch_add_parametric_curve_operation(
            conn, True, "Doc", "Sk",
            "10*math.cos(t)", "10*math.sin(t)", 0, 2 * math.pi
        )
        assert_code_compiles(_code(conn))

    def test_expressions_in_code(self):
        conn = _ok_conn()
        sketch_add_parametric_curve_operation(
            conn, True, "Doc", "Sk",
            "10*math.cos(t)", "5*math.sin(t)", 0, math.pi
        )
        code = _code(conn)
        assert_code_contains(code, "10*math.cos(t)", "5*math.sin(t)")

    def test_samples_too_low_returns_error(self):
        resp = sketch_add_parametric_curve_operation(
            _ok_conn(), True, "Doc", "Sk", "t", "t", 0, 1, samples=5
        )
        assert "samples must be" in _text(resp)

    def test_t_start_ge_t_end_returns_error(self):
        resp = sketch_add_parametric_curve_operation(
            _ok_conn(), True, "Doc", "Sk", "t", "t", 1.0, 0.5
        )
        assert "t_start" in _text(resp)

    def test_interpolate_called(self):
        conn = _ok_conn()
        sketch_add_parametric_curve_operation(
            conn, True, "Doc", "Sk", "t", "t", 0, 1
        )
        assert_code_contains(_code(conn), "interpolate")

    def test_involute_expressions_compile(self):
        """Validate that a true involute can be expressed via parametric_curve."""
        conn = _ok_conn()
        sketch_add_parametric_curve_operation(
            conn, True, "Doc", "Sk",
            "10*(math.cos(t) + t*math.sin(t))",
            "10*(math.sin(t) - t*math.cos(t))",
            0.0, 1.2, samples=50,
        )
        assert_code_compiles(_code(conn))

    def test_involute_expressions_correct(self):
        """50 samples of the involute expression must lie on the analytic involute."""
        r_b = 10.0
        t0, t1, n = 0.0, 1.2, 50
        ts = [t0 + (t1 - t0) * i / n for i in range(n + 1)]
        pts = [(r_b * (math.cos(t) + t * math.sin(t)),
                r_b * (math.sin(t) - t * math.cos(t))) for t in ts]
        # Direct (exact) check — no grid search, no quantization error.
        assert_on_involute_direct(pts, r_b)


# ---------------------------------------------------------------------------
# P1-10  sketch_import_points
# ---------------------------------------------------------------------------

class TestSketchImportPoints:
    _pts = [{"x": 0, "y": 0}, {"x": 5, "y": 5}, {"x": 10, "y": 0}]

    def test_success(self):
        resp = sketch_import_points_operation(_ok_conn(), True, "Doc", "Sk", self._pts)
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        sketch_import_points_operation(conn, True, "Doc", "Sk", self._pts)
        assert_code_compiles(_code(conn))

    def test_point_api_called(self):
        conn = _ok_conn()
        sketch_import_points_operation(conn, True, "Doc", "Sk", self._pts)
        assert_code_contains(_code(conn), "Part.Point")

    def test_all_coordinates_present(self):
        conn = _ok_conn()
        sketch_import_points_operation(conn, True, "Doc", "Sk", self._pts)
        code = _code(conn)
        assert_code_contains(code, "(0,0)", "(5,5)", "(10,0)")


# ---------------------------------------------------------------------------
# P1-11  sketch_toggle_construction
# ---------------------------------------------------------------------------

class TestSketchToggleConstruction:
    def test_success(self):
        resp = sketch_toggle_construction_operation(_ok_conn(), True, "Doc", "Sk", [0, 1, 2])
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        sketch_toggle_construction_operation(conn, True, "Doc", "Sk", [0, 1, 2])
        assert_code_compiles(_code(conn))

    def test_toggle_api_called(self):
        conn = _ok_conn()
        sketch_toggle_construction_operation(conn, True, "Doc", "Sk", [0])
        assert_code_contains(_code(conn), "toggleConstruction")

    def test_indices_in_code(self):
        conn = _ok_conn()
        sketch_toggle_construction_operation(conn, True, "Doc", "Sk", [3, 5])
        assert_code_contains(_code(conn), "[3, 5]")
