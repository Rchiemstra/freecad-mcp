"""Runtime regressions for registered tools after native-authority cutover."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from freecad_mcp.collaboration_client import CollaborationClient
from freecad_mcp.server_ops.tool_dependencies import ToolDependencies
from freecad_mcp.server_state import ServerState
from tests.helpers.response import response_text
from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

pytestmark = pytest.mark.unit


def _tool_function(mcp, name: str):
    manager = getattr(mcp, "_tool_manager", None)
    registry = getattr(manager, "_tools", None) or getattr(manager, "tools", None)
    tool = registry[name]
    return getattr(tool, "fn", None) or getattr(tool, "function", None)


def test_registered_run_transaction_is_retired_in_every_runtime_mode(
    monkeypatch,
) -> None:
    bootstrap_unit_test_runtime()
    from freecad_mcp import tools_advanced_a
    from freecad_mcp.generated.capabilities.register_modules import tools_advanced_a as generated_tools_advanced_a
    from freecad_mcp.instrumented_server import InstrumentedFastMCP

    state = ServerState()
    connection = MagicMock(name="FreeCADConnection")
    mcp = InstrumentedFastMCP("phase18-run-transaction")
    monkeypatch.setattr(generated_tools_advanced_a, "server_connection", lambda: connection)
    dependencies = ToolDependencies(
        state=state,
        get_freecad_connection=lambda: connection,
        recovery_compatibility=None,
        collaboration=CollaborationClient(connection),
        document_selector_input=dict,
    )
    exports = tools_advanced_a.register(mcp, dependencies=dependencies)

    result = _tool_function(mcp, "run_transaction")(None, "Model", "edit", "pass")
    assert "RUN_TRANSACTION_RETIRED" in str(result.structuredContent)
    assert "retired" in response_text(result)
    state.rpc_session.mark_connected("auth-secret")
    authenticated = _tool_function(mcp, "run_transaction")(
        None, "Model", "edit", "pass"
    )
    assert "RUN_TRANSACTION_RETIRED" in str(authenticated.structuredContent)
    assert exports["run_transaction"] is _tool_function(mcp, "run_transaction")
    connection.invoke_rpc.assert_not_called()
