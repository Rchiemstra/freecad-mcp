"""get_runtime_info must show a worker that cannot run jobs.

get_worker_status said "unavailable: revision identity mismatch" while
get_runtime_info listed no unavailable or degraded tools in the same session.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from freecad_mcp.generated.capabilities.register_modules import tools_runtime_info
from freecad_mcp.server_state import ServerState
from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

pytestmark = pytest.mark.unit


def _payload(monkeypatch, worker_status):
    bootstrap_unit_test_runtime()
    connection = MagicMock(name="FreeCADConnection")
    connection.get_instance_info.return_value = {}
    connection.get_worker_status.return_value = worker_status
    monkeypatch.setattr(tools_runtime_info, "server_state", lambda: ServerState())
    monkeypatch.setattr(tools_runtime_info, "server_connection", lambda: connection)
    return tools_runtime_info._runtime_info_payload()


def test_an_unavailable_worker_degrades_read_only_execution(monkeypatch):
    payload = _payload(
        monkeypatch,
        {"available": False, "state": "unavailable", "last_error": "revision identity mismatch"},
    )

    degraded = payload["tool_availability"]["degraded_tools"]
    worker = [item for item in degraded if item["tool"] == "execute_code"]
    assert worker and "revision identity mismatch" in worker[0]["limitation"]


def test_an_available_worker_adds_nothing(monkeypatch):
    payload = _payload(monkeypatch, {"available": True, "state": "idle"})

    tools = [item["tool"] for item in payload["tool_availability"]["degraded_tools"]]
    assert "execute_code" not in tools
