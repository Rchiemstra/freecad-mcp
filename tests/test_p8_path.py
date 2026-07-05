"""
Tests for path wire and pipe sweep operations.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from mcp.types import TextContent

from freecad_mcp.operations.p7_assembly import (
    build_path_wire_operation,
    sweep_pipe_operation,
)
from tests.helpers.geometric import assert_code_compiles, assert_code_contains


def _ok_conn(output: str = '{"ok": true}'):
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {
        "success": True,
        "message": "Python code execution scheduled. \nOutput: " + output,
        "recompute_errors": [],
    }
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


class TestBuildPathWire:
    def test_compiles_and_builds_sorted_wire(self):
        conn = _ok_conn()
        build_path_wire_operation(
            conn,
            True,
            "Doc",
            "CablePathWireLower",
            [
                {"sketch": "Part2", "geo_index": 0, "reverse": False},
                {
                    "type": "bridge",
                    "from": "prev_end",
                    "to": {"sketch": "Route", "geo_index": 0, "end": "start"},
                },
                {"sketch": "Route", "geo_index": 0, "reverse": True},
            ],
            tolerance_mm=0.5,
            container="CableVisualization",
            if_exists="replace",
        )
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(
            code,
            "toShape()",
            "getGlobalPlacement",
            "bridge gap",
            "Part.sortEdges",
            "Part.Wire",
            "length_mm",
            "check_ok",
        )

    def test_invalid_if_exists(self):
        resp = build_path_wire_operation(_ok_conn(), True, "Doc", "Wire", [], if_exists="bad")
        assert "if_exists" in _text(resp)

    def test_failure_propagates(self):
        resp = build_path_wire_operation(_fail_conn(), True, "Doc", "Wire", [])
        assert "oops" in _text(resp)


class TestSweepPipe:
    def test_compiles_and_uses_pipe_shell(self):
        conn = _ok_conn()
        sweep_pipe_operation(
            conn,
            True,
            "Doc",
            "CablePathWireLower",
            1.75,
            "CableLower_1p75mm",
            profile_mode="frenet",
            color=[0.85, 0.15, 0.15],
            container="CableVisualization",
            if_exists="replace",
        )
        code = _code(conn)
        assert_code_compiles(code)
        assert_code_contains(
            code,
            "Part.makeCircle",
            "makePipeShell",
            "profile_mode",
            "min_bend_radius_mm",
            "volume_mm3",
            "check_ok",
        )

    def test_rejects_bad_if_exists(self):
        resp = sweep_pipe_operation(_ok_conn(), True, "Doc", "Wire", 1.75, "Cable", if_exists="bad")
        assert "if_exists" in _text(resp)

    def test_failure_propagates(self):
        resp = sweep_pipe_operation(_fail_conn(), True, "Doc", "Wire", 1.75, "Cable")
        assert "oops" in _text(resp)
