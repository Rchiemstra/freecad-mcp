"""
Tests for P2 sketch editing operations.

Layer-A: Schema / error propagation
Layer-B: Code-fragment and API-call checks
"""
from __future__ import annotations

from unittest.mock import MagicMock

from mcp.types import TextContent

from freecad_mcp.operations.p2_editing import (
    sketch_extend_operation,
    sketch_fillet_operation,
    sketch_offset_operation,
    sketch_split_operation,
    sketch_symmetry_operation,
    sketch_trim_operation,
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
    content = response.content if hasattr(response, "content") else response
    return " ".join(item.text for item in content if isinstance(item, TextContent))


# ---------------------------------------------------------------------------
# P2-1  sketch_trim
# ---------------------------------------------------------------------------

class TestSketchTrim:
    def test_success(self):
        resp = sketch_trim_operation(_ok_conn(), True, "Doc", "Sk", 0, 5.0, 0.0)
        assert _text(resp)

    def test_failure(self):
        resp = sketch_trim_operation(_fail_conn(), True, "Doc", "Sk", 0, 5.0, 0.0)
        assert "oops" in _text(resp) or "Failed" in _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        sketch_trim_operation(conn, True, "Doc", "Sk", 0, 5.0, 0.0)
        assert_code_compiles(_code(conn))

    def test_trim_api_called(self):
        conn = _ok_conn()
        sketch_trim_operation(conn, True, "Doc", "Sk", 2, 5.0, 3.0)
        assert_code_contains(_code(conn), "_sk.trim")

    def test_geo_index_in_code(self):
        conn = _ok_conn()
        sketch_trim_operation(conn, True, "Doc", "Sk", 7, 0.0, 0.0)
        assert_code_contains(_code(conn), "7")

    def test_point_vector_in_code(self):
        conn = _ok_conn()
        sketch_trim_operation(conn, True, "Doc", "Sk", 0, 3.5, 2.5)
        assert_code_contains(_code(conn), "3.5", "2.5")

    def test_recompute_called(self):
        conn = _ok_conn()
        sketch_trim_operation(conn, True, "Doc", "Sk", 0, 0.0, 0.0)
        assert_code_contains(_code(conn), "_doc.recompute()")


# ---------------------------------------------------------------------------
# P2-2  sketch_extend
# ---------------------------------------------------------------------------

class TestSketchExtend:
    def test_success(self):
        resp = sketch_extend_operation(_ok_conn(), True, "Doc", "Sk", 0, 5.0)
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        sketch_extend_operation(conn, True, "Doc", "Sk", 0, 5.0)
        assert_code_compiles(_code(conn))

    def test_extend_api_called(self):
        conn = _ok_conn()
        sketch_extend_operation(conn, True, "Doc", "Sk", 1, 10.0)
        assert_code_contains(_code(conn), "_sk.extend")

    def test_increment_in_code(self):
        conn = _ok_conn()
        sketch_extend_operation(conn, True, "Doc", "Sk", 1, 7.5)
        assert_code_contains(_code(conn), "7.5")

    def test_end_point_default(self):
        conn = _ok_conn()
        sketch_extend_operation(conn, True, "Doc", "Sk", 0, 1.0)
        assert_code_contains(_code(conn), "2")

    def test_end_point_custom(self):
        conn = _ok_conn()
        sketch_extend_operation(conn, True, "Doc", "Sk", 0, 1.0, end_point=1)
        assert_code_contains(_code(conn), "1")


# ---------------------------------------------------------------------------
# P2-3  sketch_split
# ---------------------------------------------------------------------------

class TestSketchSplit:
    def test_success(self):
        resp = sketch_split_operation(_ok_conn(), True, "Doc", "Sk", 0, 5.0, 0.0)
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        sketch_split_operation(conn, True, "Doc", "Sk", 0, 5.0, 0.0)
        assert_code_compiles(_code(conn))

    def test_split_api_called(self):
        conn = _ok_conn()
        sketch_split_operation(conn, True, "Doc", "Sk", 3, 2.0, 4.0)
        assert_code_contains(_code(conn), "_sk.split")

    def test_point_in_code(self):
        conn = _ok_conn()
        sketch_split_operation(conn, True, "Doc", "Sk", 0, 1.1, 2.2)
        assert_code_contains(_code(conn), "1.1", "2.2")


# ---------------------------------------------------------------------------
# P2-4  sketch_fillet
# ---------------------------------------------------------------------------

class TestSketchFillet:
    def test_success(self):
        resp = sketch_fillet_operation(_ok_conn(), True, "Doc", "Sk", 0, 1, 2.0)
        assert _text(resp)

    def test_negative_radius_error(self):
        resp = sketch_fillet_operation(_ok_conn(), True, "Doc", "Sk", 0, 1, -1.0)
        assert "radius must be" in _text(resp)

    def test_zero_radius_error(self):
        resp = sketch_fillet_operation(_ok_conn(), True, "Doc", "Sk", 0, 1, 0.0)
        assert "radius must be" in _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        sketch_fillet_operation(conn, True, "Doc", "Sk", 0, 1, 3.0)
        assert_code_compiles(_code(conn))

    def test_fillet_api_called(self):
        conn = _ok_conn()
        sketch_fillet_operation(conn, True, "Doc", "Sk", 0, 1, 3.0)
        assert_code_contains(_code(conn), "_sk.fillet")

    def test_radius_in_code(self):
        conn = _ok_conn()
        sketch_fillet_operation(conn, True, "Doc", "Sk", 0, 1, 4.5)
        assert_code_contains(_code(conn), "4.5")

    def test_geo_indices_in_code(self):
        conn = _ok_conn()
        sketch_fillet_operation(conn, True, "Doc", "Sk", 2, 5, 1.0)
        code = _code(conn)
        assert_code_contains(code, "2", "5")


# ---------------------------------------------------------------------------
# P2-5  sketch_offset
# ---------------------------------------------------------------------------

class TestSketchOffset:
    def test_success(self):
        resp = sketch_offset_operation(_ok_conn(), True, "Doc", "Sk", [0, 1], 2.0)
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        sketch_offset_operation(conn, True, "Doc", "Sk", [0, 1], 2.0)
        assert_code_compiles(_code(conn))

    def test_offset_in_code(self):
        conn = _ok_conn()
        sketch_offset_operation(conn, True, "Doc", "Sk", [0], 3.5)
        assert_code_contains(_code(conn), "3.5")

    def test_indices_in_code(self):
        conn = _ok_conn()
        sketch_offset_operation(conn, True, "Doc", "Sk", [2, 4], 1.0)
        assert_code_contains(_code(conn), "[2, 4]")


# ---------------------------------------------------------------------------
# P2-6  sketch_symmetry
# ---------------------------------------------------------------------------

class TestSketchSymmetry:
    def test_success(self):
        resp = sketch_symmetry_operation(_ok_conn(), True, "Doc", "Sk", [0, 1], 5)
        assert _text(resp)

    def test_compiles(self):
        conn = _ok_conn()
        sketch_symmetry_operation(conn, True, "Doc", "Sk", [0, 1], 5)
        assert_code_compiles(_code(conn))

    def test_sym_geo_in_code(self):
        conn = _ok_conn()
        sketch_symmetry_operation(conn, True, "Doc", "Sk", [0], 7)
        assert_code_contains(_code(conn), "7")

    def test_fallback_constraint_path(self):
        conn = _ok_conn()
        sketch_symmetry_operation(conn, True, "Doc", "Sk", [0, 1], 5)
        assert_code_contains(_code(conn), "Symmetric")

    def test_indices_in_code(self):
        conn = _ok_conn()
        sketch_symmetry_operation(conn, True, "Doc", "Sk", [3, 4], 10)
        assert_code_contains(_code(conn), "[3, 4]")
