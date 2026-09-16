"""
Tests for path wire and pipe sweep operations.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from mcp.types import TextContent

from freecad_mcp._shared.protocol.build_path_wire_contract import (
    make_build_path_wire_failure,
    make_build_path_wire_success,
)
from freecad_mcp._shared.protocol.sweep_pipe_contract import (
    make_sweep_pipe_failure,
    make_sweep_pipe_success,
)
from freecad_mcp.operations.p7_assembly import (
    build_path_wire_operation,
    sweep_pipe_operation,
)


def _ok_conn():
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.build_path_wire.return_value = make_build_path_wire_success("CablePathWireLower")
    conn.sweep_pipe.return_value = make_sweep_pipe_success("CableLower_1p75mm")
    return conn


def _fail_conn(error: str = "oops"):
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.build_path_wire.return_value = make_build_path_wire_failure("FAILED", error)
    conn.sweep_pipe.return_value = make_sweep_pipe_failure("FAILED", error)
    return conn


def _text(response) -> str:
    content = response.content if hasattr(response, "content") else response
    return " ".join(item.text for item in content if isinstance(item, TextContent))


class TestBuildPathWire:
    def test_compiles_and_builds_sorted_wire(self):
        conn = _ok_conn()
        segments = [
            {"sketch": "Part2", "geo_index": 0, "reverse": False},
            {
                "type": "bridge",
                "from": "prev_end",
                "to": {"sketch": "Route", "geo_index": 0, "end": "start"},
            },
            {"sketch": "Route", "geo_index": 0, "reverse": True},
        ]
        resp = build_path_wire_operation(
            conn,
            True,
            "Doc",
            "CablePathWireLower",
            segments,
            tolerance_mm=0.5,
            container="CableVisualization",
            if_exists="replace",
        )
        assert not resp.isError
        conn.build_path_wire.assert_called_once_with(
            "Doc",
            "CablePathWireLower",
            segments,
            0.5,
            "CableVisualization",
            "replace",
        )
        conn.execute_code.assert_not_called()

    def test_invalid_if_exists(self):
        resp = build_path_wire_operation(_ok_conn(), True, "Doc", "Wire", [], if_exists="bad")
        assert "if_exists" in _text(resp)

    def test_failure_propagates(self):
        resp = build_path_wire_operation(
            _fail_conn(), True, "Doc", "Wire", [{"sketch": "Seed", "geo_index": 0}]
        )
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
        conn.sweep_pipe.assert_called_once_with(
            "Doc",
            "CablePathWireLower",
            1.75,
            "CableLower_1p75mm",
            "frenet",
            [0.85, 0.15, 0.15],
            "CableVisualization",
            "replace",
        )
        conn.execute_code.assert_not_called()

    def test_rejects_bad_if_exists(self):
        resp = sweep_pipe_operation(_ok_conn(), True, "Doc", "Wire", 1.75, "Cable", if_exists="bad")
        assert "if_exists" in _text(resp)

    def test_failure_propagates(self):
        resp = sweep_pipe_operation(_fail_conn(), True, "Doc", "Wire", 1.75, "Cable")
        assert "oops" in _text(resp)
