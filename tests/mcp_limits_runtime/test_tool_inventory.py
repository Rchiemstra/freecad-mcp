"""Registered MCP tool inventory for runtime limits diagnostics."""

from __future__ import annotations

import pytest

from freecad_mcp.generated.capabilities.register_modules.tools_runtime_info import (
    _RPC_V2_ONLY_TOOLS,
)
from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

pytestmark = pytest.mark.unit

_UNREGISTERED_V2_GATE_TOOLS = frozenset(
    {
        "capture_view_sequence",
        "capture_view_sequence_to_disk",
        "get_active_screenshot",
    }
)


def _tool_registry(mcp) -> dict:
    manager = getattr(mcp, "_tool_manager", None)
    assert manager is not None
    registry = getattr(manager, "_tools", None) or getattr(manager, "tools", None)
    assert isinstance(registry, dict)
    return registry


@pytest.fixture(scope="module")
def server_module():
    bootstrap_unit_test_runtime()
    from freecad_mcp import server

    return server


def test_registered_tool_names_are_sorted_and_include_v2_gate_subset(server_module) -> None:
    registry = _tool_registry(server_module.mcp)
    registered = sorted(registry)

    assert registered
    assert registered == sorted(registered)
    assert len(_RPC_V2_ONLY_TOOLS) == 21

    registered_gate = sorted(set(registered).intersection(_RPC_V2_ONLY_TOOLS))
    expected_registered_gate = sorted(
        _RPC_V2_ONLY_TOOLS.difference(_UNREGISTERED_V2_GATE_TOOLS)
    )
    assert registered_gate == expected_registered_gate
    assert "save_document" in registered
    assert "undo" in registered
    assert "get_runtime_info" in registered
