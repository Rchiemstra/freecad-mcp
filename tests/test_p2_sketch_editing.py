"""
Tests for P2 sketch editing operations.

Layer-A: typed RPC propagation
Layer-B: request routing
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


def _typed_success():
    return {
        "contract_version": 1,
        "success": True,
        "ok": True,
        "outcome": "committed",
        "committed": True,
        "retry_safe": False,
        "sketch": "Sk",
        "geometry_indices": [0],
    }


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


def _ok_conn(method: str | None = None):
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    if method is not None:
        getattr(conn, method).return_value = _typed_success()
    else:
        conn.execute_code.return_value = {"success": True, "message": "done", "recompute_errors": []}
    return conn


def _fail_conn(method: str):
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    getattr(conn, method).return_value = _typed_failure()
    return conn


def _text(response) -> str:
    content = response.content if hasattr(response, "content") else response
    return " ".join(item.text for item in content if isinstance(item, TextContent))


def _code(conn) -> str:
    return conn.execute_code.call_args[0][0]


class TestSketchTrim:
    def test_success(self):
        resp = sketch_trim_operation(_ok_conn("sketch_trim"), True, "Doc", "Sk", 0, 5.0, 0.0)
        assert _text(resp)

    def test_failure(self):
        resp = sketch_trim_operation(_fail_conn("sketch_trim"), True, "Doc", "Sk", 0, 5.0, 0.0)
        assert "oops" in _text(resp) or "Failed" in _text(resp)

    def test_routes_typed_rpc(self):
        conn = _ok_conn("sketch_trim")
        sketch_trim_operation(conn, True, "Doc", "Sk", 2, 5.0, 3.0)
        conn.sketch_trim.assert_called_once_with("Doc", "Sk", 2, 5.0, 3.0)


class TestSketchExtend:
    def test_success(self):
        resp = sketch_extend_operation(_ok_conn("sketch_extend"), True, "Doc", "Sk", 0, 5.0)
        assert _text(resp)

    def test_routes_typed_rpc(self):
        conn = _ok_conn("sketch_extend")
        sketch_extend_operation(conn, True, "Doc", "Sk", 1, 7.5, end_point=1)
        conn.sketch_extend.assert_called_once_with("Doc", "Sk", 1, 7.5, 1)


class TestSketchSplit:
    def test_success(self):
        resp = sketch_split_operation(_ok_conn("sketch_split"), True, "Doc", "Sk", 0, 5.0, 0.0)
        assert _text(resp)

    def test_routes_typed_rpc(self):
        conn = _ok_conn("sketch_split")
        sketch_split_operation(conn, True, "Doc", "Sk", 3, 2.0, 4.0)
        conn.sketch_split.assert_called_once_with("Doc", "Sk", 3, 2.0, 4.0)


class TestSketchFillet:
    def test_success(self):
        resp = sketch_fillet_operation(_ok_conn("sketch_fillet"), True, "Doc", "Sk", 0, 1, 2.0)
        assert _text(resp)

    def test_negative_radius_error(self):
        resp = sketch_fillet_operation(_ok_conn("sketch_fillet"), True, "Doc", "Sk", 0, 1, -1.0)
        assert "radius must be" in _text(resp)

    def test_zero_radius_error(self):
        resp = sketch_fillet_operation(_ok_conn("sketch_fillet"), True, "Doc", "Sk", 0, 1, 0.0)
        assert "radius must be" in _text(resp)

    def test_routes_typed_rpc(self):
        conn = _ok_conn("sketch_fillet")
        sketch_fillet_operation(conn, True, "Doc", "Sk", 2, 5, 4.5)
        conn.sketch_fillet.assert_called_once_with("Doc", "Sk", 2, 5, 4.5)


class TestSketchOffset:
    def test_success(self):
        resp = sketch_offset_operation(_ok_conn("sketch_offset"), True, "Doc", "Sk", [0, 1], 2.0)
        assert _text(resp)

    def test_zero_offset_error(self):
        resp = sketch_offset_operation(_ok_conn("sketch_offset"), True, "Doc", "Sk", [0], 0.0)
        assert "offset must be" in _text(resp)

    def test_routes_typed_rpc(self):
        conn = _ok_conn("sketch_offset")
        sketch_offset_operation(conn, True, "Doc", "Sk", [0, 1], 2.0, copy=False, construction=True)
        conn.sketch_offset.assert_called_once_with("Doc", "Sk", [0, 1], 2.0, False, True)


class TestSketchSymmetry:
    def test_success(self):
        resp = sketch_symmetry_operation(_ok_conn("sketch_symmetry"), True, "Doc", "Sk", [0, 1], 5)
        assert _text(resp)

    def test_routes_typed_rpc(self):
        conn = _ok_conn("sketch_symmetry")
        sketch_symmetry_operation(conn, True, "Doc", "Sk", [3, 4], 10, copy=False)
        conn.sketch_symmetry.assert_called_once_with("Doc", "Sk", [3, 4], 10, False)
