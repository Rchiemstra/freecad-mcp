"""
Tests for P3 3D feature operations.

Layer-A: Schema / error propagation
Layer-B: Code-fragment and API-call checks
"""
from __future__ import annotations

from unittest.mock import MagicMock

from mcp.types import TextContent

from freecad_mcp.operations.p3_features import (
    boolean_difference_operation,
    boolean_intersection_operation,
    boolean_union_operation,
    chamfer_feature_operation,
    fillet_feature_operation,
    helical_sweep_feature_operation,
    loft_feature_operation,
    revolve_feature_operation,
    sweep_feature_operation,
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
# P3-1  revolve_feature
# ---------------------------------------------------------------------------

class TestRevolveFeature:
    def test_success(self):
        resp = revolve_feature_operation(_ok_conn(), True, "Doc", "Sketch", "Rev1")
        assert _text(resp)

    def test_failure(self):
        resp = revolve_feature_operation(_fail_conn(), True, "Doc", "Sketch", "Rev1")
        assert "oops" in _text(resp) or "Failed" in _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        revolve_feature_operation(conn, True, "Doc", "Sketch", "Rev1")
        assert_code_compiles(_code(conn))

    def test_revolution_type(self):
        conn = _ok_conn()
        revolve_feature_operation(conn, True, "Doc", "Sketch", "Rev1")
        assert_code_contains(_code(conn), "PartDesign::Revolution")

    def test_angle_in_code(self):
        conn = _ok_conn()
        revolve_feature_operation(conn, True, "Doc", "Sketch", "Rev1", angle=180.0)
        assert_code_contains(_code(conn), "180.0")

    def test_axis_in_code(self):
        conn = _ok_conn()
        revolve_feature_operation(conn, True, "Doc", "Sketch", "Rev1", axis="Z_Axis")
        assert_code_contains(_code(conn), "Z_Axis")

    def test_sketch_lookup(self):
        conn = _ok_conn()
        revolve_feature_operation(conn, True, "Doc", "MySketch", "Rev1")
        assert_code_contains(_code(conn), "MySketch")

    def test_recompute_called(self):
        conn = _ok_conn()
        revolve_feature_operation(conn, True, "Doc", "Sketch", "Rev1")
        assert_code_contains(_code(conn), "_doc.recompute()")


# ---------------------------------------------------------------------------
# P3-2  loft_feature
# ---------------------------------------------------------------------------

class TestLoftFeature:
    _sketches = ["Sketch1", "Sketch2", "Sketch3"]

    def test_success(self):
        resp = loft_feature_operation(_ok_conn(), True, "Doc", self._sketches, "Loft1")
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        loft_feature_operation(conn, True, "Doc", self._sketches, "Loft1")
        assert_code_compiles(_code(conn))

    def test_loft_type(self):
        conn = _ok_conn()
        loft_feature_operation(conn, True, "Doc", self._sketches, "Loft1")
        assert_code_contains(_code(conn), "AdditiveLoft")

    def test_sections_set(self):
        conn = _ok_conn()
        loft_feature_operation(conn, True, "Doc", self._sketches, "Loft1")
        assert_code_contains(_code(conn), "Sections")

    def test_sketch_names_in_code(self):
        conn = _ok_conn()
        loft_feature_operation(conn, True, "Doc", self._sketches, "Loft1")
        code = _code(conn)
        for s in self._sketches:
            assert_code_contains(code, s)


# ---------------------------------------------------------------------------
# P3-3  sweep_feature
# ---------------------------------------------------------------------------

class TestSweepFeature:
    def test_success(self):
        resp = sweep_feature_operation(_ok_conn(), True, "Doc", "Profile", "Spine", "Sweep1")
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        sweep_feature_operation(conn, True, "Doc", "Profile", "Spine", "Sweep1")
        assert_code_compiles(_code(conn))

    def test_pipe_type(self):
        conn = _ok_conn()
        sweep_feature_operation(conn, True, "Doc", "Profile", "Spine", "Sweep1")
        assert_code_contains(_code(conn), "AdditivePipe")

    def test_profile_and_spine_in_code(self):
        conn = _ok_conn()
        sweep_feature_operation(conn, True, "Doc", "MyProfile", "MySpine", "Sweep1")
        code = _code(conn)
        assert_code_contains(code, "MyProfile", "MySpine")


# ---------------------------------------------------------------------------
# P3-4  helical_sweep_feature
# ---------------------------------------------------------------------------

class TestHelicalSweepFeature:
    def test_success(self):
        resp = helical_sweep_feature_operation(
            _ok_conn(), True, "Doc", "Profile", "Helix1", 2.0, 10.0, 5.0
        )
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        helical_sweep_feature_operation(conn, True, "Doc", "Profile", "Helix1", 2.0, 10.0, 5.0)
        assert_code_compiles(_code(conn))

    def test_helix_type(self):
        conn = _ok_conn()
        helical_sweep_feature_operation(conn, True, "Doc", "Profile", "Helix1", 2.0, 10.0, 5.0)
        assert_code_contains(_code(conn), "AdditiveHelix")

    def test_pitch_in_code(self):
        conn = _ok_conn()
        helical_sweep_feature_operation(conn, True, "Doc", "Profile", "Helix1", 3.5, 10.0, 5.0)
        assert_code_contains(_code(conn), "3.5")

    def test_height_in_code(self):
        conn = _ok_conn()
        helical_sweep_feature_operation(conn, True, "Doc", "Profile", "Helix1", 2.0, 20.0, 5.0)
        assert_code_contains(_code(conn), "20.0")


# ---------------------------------------------------------------------------
# P3-5  fillet_feature
# ---------------------------------------------------------------------------

class TestFilletFeature:
    def test_success(self):
        resp = fillet_feature_operation(_ok_conn(), True, "Doc", "Body1", ["Edge1", "Edge2"], 1.0)
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        fillet_feature_operation(conn, True, "Doc", "Body1", ["Edge1"], 1.0)
        assert_code_compiles(_code(conn))

    def test_fillet_type(self):
        conn = _ok_conn()
        fillet_feature_operation(conn, True, "Doc", "Body1", ["Edge1"], 1.0)
        assert_code_contains(_code(conn), "Fillet")

    def test_radius_in_code(self):
        conn = _ok_conn()
        fillet_feature_operation(conn, True, "Doc", "Body1", ["Edge1"], 2.5)
        assert_code_contains(_code(conn), "2.5")


# ---------------------------------------------------------------------------
# P3-6  chamfer_feature
# ---------------------------------------------------------------------------

class TestChamferFeature:
    def test_success(self):
        resp = chamfer_feature_operation(_ok_conn(), True, "Doc", "Body1", ["Edge1"], 1.0)
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        chamfer_feature_operation(conn, True, "Doc", "Body1", ["Edge1"], 1.0)
        assert_code_compiles(_code(conn))

    def test_chamfer_type(self):
        conn = _ok_conn()
        chamfer_feature_operation(conn, True, "Doc", "Body1", ["Edge1"], 1.0)
        assert_code_contains(_code(conn), "Chamfer")

    def test_size_in_code(self):
        conn = _ok_conn()
        chamfer_feature_operation(conn, True, "Doc", "Body1", ["Edge1"], 3.0)
        assert_code_contains(_code(conn), "3.0")


# ---------------------------------------------------------------------------
# P3-7  boolean_union
# ---------------------------------------------------------------------------

class TestBooleanUnion:
    def test_success(self):
        resp = boolean_union_operation(_ok_conn(), True, "Doc", "Base1", "Tool1", "Union1")
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        boolean_union_operation(conn, True, "Doc", "Base1", "Tool1", "Union1")
        assert_code_compiles(_code(conn))

    def test_fuse_type(self):
        conn = _ok_conn()
        boolean_union_operation(conn, True, "Doc", "Base1", "Tool1", "Union1")
        assert_code_contains(_code(conn), "Part::Fuse")

    def test_base_and_tool_in_code(self):
        conn = _ok_conn()
        boolean_union_operation(conn, True, "Doc", "Obj_A", "Obj_B", "Union1")
        code = _code(conn)
        assert_code_contains(code, "Obj_A", "Obj_B")


# ---------------------------------------------------------------------------
# P3-8  boolean_difference
# ---------------------------------------------------------------------------

class TestBooleanDifference:
    def test_success(self):
        resp = boolean_difference_operation(_ok_conn(), True, "Doc", "Base1", "Tool1", "Cut1")
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        boolean_difference_operation(conn, True, "Doc", "Base1", "Tool1", "Cut1")
        assert_code_compiles(_code(conn))

    def test_cut_type(self):
        conn = _ok_conn()
        boolean_difference_operation(conn, True, "Doc", "Base1", "Tool1", "Cut1")
        assert_code_contains(_code(conn), "Part::Cut")


# ---------------------------------------------------------------------------
# P3-9  boolean_intersection
# ---------------------------------------------------------------------------

class TestBooleanIntersection:
    def test_success(self):
        resp = boolean_intersection_operation(_ok_conn(), True, "Doc", "Base1", "Tool1", "Common1")
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        boolean_intersection_operation(conn, True, "Doc", "Base1", "Tool1", "Common1")
        assert_code_compiles(_code(conn))

    def test_common_type(self):
        conn = _ok_conn()
        boolean_intersection_operation(conn, True, "Doc", "Base1", "Tool1", "Common1")
        assert_code_contains(_code(conn), "Part::Common")
