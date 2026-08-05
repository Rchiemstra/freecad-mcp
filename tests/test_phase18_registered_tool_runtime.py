"""Runtime regressions for registered tools after native-authority cutover."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tests.helpers.response import response_text
from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

pytestmark = pytest.mark.unit


def _tool_function(mcp, name: str):
    manager = getattr(mcp, "_tool_manager", None)
    registry = getattr(manager, "_tools", None) or getattr(manager, "tools", None)
    tool = registry[name]
    return getattr(tool, "fn", None) or getattr(tool, "function", None)


def test_registered_run_transaction_uses_auth_session_not_retired_lease_state(
    monkeypatch,
) -> None:
    bootstrap_unit_test_runtime()
    from freecad_mcp.instrumented_server import InstrumentedFastMCP
    from freecad_mcp.server_state import ServerState
    from freecad_mcp import tools_advanced_a

    state = ServerState()
    connection = MagicMock(name="FreeCADConnection")
    mcp = InstrumentedFastMCP("phase18-run-transaction")
    monkeypatch.setattr(tools_advanced_a, "server_connection", lambda: connection)
    exports = tools_advanced_a.register(
        mcp,
        state=state,
        get_freecad_connection=lambda: connection,
        stale_recovery=MagicMock(),
    )

    state.rpc_session.mark_connected("auth-secret")
    result = _tool_function(mcp, "run_transaction")(
        None, "Model", "edit", "pass"
    )

    assert "disabled in authenticated lease mode" in response_text(result)
    assert exports["run_transaction"] is _tool_function(mcp, "run_transaction")
    connection.invoke_rpc.assert_not_called()
