"""Runtime diagnostics must report the connection established by this call."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from freecad_mcp.generated.capabilities.inline import tools_runtime_info as inline
from freecad_mcp.generated.capabilities.register_modules import tools_runtime_info as registered
from freecad_mcp.instrumented_server import InstrumentedFastMCP
from freecad_mcp.server_state import ServerState
from tests.mcp_limits_runtime.test_authenticated_rpc_handshake import _authenticated_manifest

pytestmark = pytest.mark.unit


@pytest.fixture(params=[registered, inline], ids=["registered", "inline"])
def runtime_module(request):
    return request.param


@pytest.mark.parametrize("restart", [False, True], ids=["first-connection", "restart"])
def test_runtime_identity_uses_refreshed_authentication(monkeypatch, runtime_module, restart):
    state = ServerState()
    current = _authenticated_manifest()
    state.authenticated_manifest = (
        replace(
            current,
            freecad_pid=1111,
            addon_runtime_id="c2f2e9fa-d897-46f0-bc7a-dc15d0d680a7",
        )
        if restart
        else None
    )
    connection = MagicMock()

    def instance_info():
        # A restarted addon refreshes authentication while servicing the RPC.
        state.authenticated_manifest = current
        return {"pid": current.freecad_pid}

    def get_connection():
        # The first connection authenticates lazily during connection lookup.
        if not restart:
            state.authenticated_manifest = current
        return connection

    connection.get_instance_info.side_effect = instance_info
    monkeypatch.setattr(runtime_module, "server_state", lambda: state)
    monkeypatch.setattr(runtime_module, "server_connection", get_connection)

    payload = runtime_module._runtime_info_payload()

    assert payload["freecad"]["pid"] == current.freecad_pid
    assert payload["addon"]["runtime_id"] == current.addon_runtime_id
    assert payload["rpc"]["authenticated_session"] is True
    assert payload["compatibility"]["compatible"] is True
    assert payload["tool_availability"]["authenticated_rpc_v2"] is True


@pytest.mark.parametrize("failure_stage", ["connection", "rpc"])
def test_runtime_diagnostics_do_not_hide_connection_failures(
    monkeypatch, runtime_module, failure_stage
):
    state = ServerState()
    state.authenticated_manifest = _authenticated_manifest()
    connection = MagicMock()
    failure = ConnectionError("FreeCAD RPC endpoint unavailable")

    def get_connection():
        if failure_stage == "connection":
            raise failure
        return connection

    connection.get_instance_info.side_effect = failure
    monkeypatch.setattr(runtime_module, "server_state", lambda: state)
    monkeypatch.setattr(runtime_module, "server_connection", get_connection)

    with pytest.raises(ConnectionError, match="FreeCAD RPC endpoint unavailable"):
        runtime_module._runtime_info_payload()


def test_registered_runtime_tool_reports_transport_failure(monkeypatch):
    state = ServerState()
    state.authenticated_manifest = _authenticated_manifest()
    connection = MagicMock()
    connection.get_instance_info.side_effect = ConnectionError("FreeCAD RPC endpoint unavailable")
    monkeypatch.setattr(registered, "server_state", lambda: state)
    monkeypatch.setattr(registered, "server_connection", lambda: connection)
    mcp = InstrumentedFastMCP("runtime-diagnostic-test")
    monkeypatch.setattr(
        mcp,
        "get_context",
        lambda: SimpleNamespace(
            request_context=SimpleNamespace(meta=None, experimental=None)
        ),
    )
    registered.register(mcp, dependencies=MagicMock())

    with pytest.raises(ToolError, match="FreeCAD RPC endpoint unavailable"):
        asyncio.run(mcp.call_tool("get_runtime_info", {}))
