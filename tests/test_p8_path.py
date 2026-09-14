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


def _typed_ok(**fields):
    payload = {
        "contract_version": 1,
        "success": True,
        "ok": True,
        "outcome": "committed",
        "committed": True,
        "retry_safe": False,
        "wire_name": "Wire",
        "solid_name": "Solid",
    }
    payload.update(fields)
    return payload


def _ok_conn(output: str = '{"ok": true}'):
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {
        "success": True,
        "message": "Python code execution scheduled. \nOutput: " + output,
        "recompute_errors": [],
    }
    conn._invoke_mutation_v2.return_value = _typed_ok()
    return conn


def _fail_conn():
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {"success": False, "error": "oops"}
    conn._invoke_mutation_v2.return_value = {
        "contract_version": 1,
        "success": False,
        "ok": False,
        "outcome": "rejected",
        "committed": False,
        "retry_safe": True,
        "error_code": "FAILED",
        "error": "oops",
    }
    return conn


def _code(conn) -> str:
    return conn.execute_code.call_args[0][0]


def _text(response) -> str:
    content = response.content if hasattr(response, "content") else response
    return " ".join(item.text for item in content if isinstance(item, TextContent))


class TestBuildPathWire:
    def test_compiles_and_builds_sorted_wire(self):
        conn = _ok_conn()
        resp = build_path_wire_operation(
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
        assert not resp.isError
        conn._invoke_mutation_v2.assert_called()
        assert conn._invoke_mutation_v2.call_args[0][0] == "build_path_wire"
        conn.execute_code.assert_not_called()

    def test_invalid_if_exists(self):
        resp = build_path_wire_operation(_ok_conn(), True, "Doc", "Wire", [], if_exists="bad")
        assert "if_exists" in _text(resp)

    def test_failure_propagates(self):
        resp = build_path_wire_operation(_fail_conn(), True, "Doc", "Wire", [{"sketch": "Seed", "geo_index": 0}])
        assert "oops" in _text(resp)


class TestSweepPipe:
    def test_compiles_and_uses_pipe_shell(self):
        conn = _ok_conn()
        resp = sweep_pipe_operation(
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
        assert not resp.isError
        conn._invoke_mutation_v2.assert_called()
        assert conn._invoke_mutation_v2.call_args[0][0] == "sweep_pipe"
        conn.execute_code.assert_not_called()

    def test_rejects_bad_if_exists(self):
        resp = sweep_pipe_operation(_ok_conn(), True, "Doc", "Wire", 1.75, "Cable", if_exists="bad")
        assert "if_exists" in _text(resp)

    def test_failure_propagates(self):
        resp = sweep_pipe_operation(_fail_conn(), True, "Doc", "Wire", 1.75, "Cable")
        assert "oops" in _text(resp)
