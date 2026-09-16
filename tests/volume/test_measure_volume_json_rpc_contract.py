"""Agent-to-FreeCAD wire contract for the ``measure_volume`` MCP operation."""

from __future__ import annotations

import asyncio
import json
import uuid
from types import SimpleNamespace

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from freecad_mcp._shared.protocol.json_rpc_client import (
    JSON_RPC_HTTP_PATH,
    JSON_RPC_PROTOCOL_HEADER,
    JSON_RPC_PROTOCOL_VALUE,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.freecad_client_ops.connection_methods.connection_headers_ops import (
    configure_rpc_session,
)
from freecad_mcp.generated.capabilities.register_modules import tools_measure_a
from freecad_mcp.instrumented_server import InstrumentedFastMCP
from freecad_mcp.instrumented_server_ops.facade_bindings import bind_instrumented_fast_mcp
from freecad_mcp.rpc_session import RpcAuthenticationSession

pytestmark = pytest.mark.unit
_DEFAULT_RESPONSE = object()
_DEFAULT_ARGUMENTS = {
    "doc_name": "AgentDocument",
    "obj_name": "Box"
}


class _RecordingFreeCADTransport:
    def __init__(self, response_result=_DEFAULT_RESPONSE) -> None:
        self.requests: list[tuple[str, dict, dict[str, str]]] = []
        self.closed = False
        self.response_result = response_result

    def request(self, path, payload, headers):
        request = json.loads(payload)
        self.requests.append((path, request, dict(headers)))
        envelope = request["params"][0]
        body_result = self.response_result
        if body_result is _DEFAULT_RESPONSE:
            from tests.volume.test_measure_volume_response import _success
            body_result = _success()
        response = {
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": {
                "ok": True,
                "request_id": envelope["request_id"],
                "result": body_result,
            },
        }
        return (
            200,
            {JSON_RPC_PROTOCOL_HEADER.lower(): (JSON_RPC_PROTOCOL_VALUE,)},
            json.dumps(response).encode(),
        )

    def close(self) -> None:
        self.closed = True


def _invoke(monkeypatch, transport, arguments):
    connection = FreeCADConnection(
        host="127.0.0.1",
        port=9875,
        mcp_instance_id="c0deface-1111-4111-8111-000000000001",
    )
    session = RpcAuthenticationSession()
    session.mark_connected(
        "test-session-token",
        session_id="test-session",
        expires_at="2099-01-01T00:00:00Z",
    )
    configure_rpc_session(connection, session)
    connection.server.transport.close()
    connection.server.transport = transport
    monkeypatch.setattr(tools_measure_a, "server_connection", lambda: connection)

    bind_instrumented_fast_mcp(InstrumentedFastMCP)
    mcp = InstrumentedFastMCP("measure_volume-contract")
    exports = {}
    tools_measure_a._register_measure_volume(mcp, dependencies=object(), exports=exports)

    async def invoke():
        async with create_connected_server_and_client_session(mcp._mcp_server) as client:
            listing = await client.list_tools()
            tool = next(tool for tool in listing.tools if tool.name == "measure_volume")
            return await client.call_tool("measure_volume", arguments)

    try:
        return asyncio.run(invoke())
    finally:
        connection.disconnect()


def test_measure_volume_sends_authenticated_json_rpc_to_freecad(monkeypatch):
    transport = _RecordingFreeCADTransport()
    result = _invoke(monkeypatch, transport, dict(_DEFAULT_ARGUMENTS))
    assert result.isError is False
    assert len(transport.requests) == 1
    path, request, headers = transport.requests[0]
    assert path == JSON_RPC_HTTP_PATH
    assert request["jsonrpc"] == "2.0"
    assert request["method"] == "invoke_v2"
    envelope = request["params"][0]
    uuid.UUID(envelope["request_id"])
    assert envelope["method"] == "measure_volume"
    assert envelope["params"]["doc_name"] == "AgentDocument"
    assert envelope["params"]["obj_name"] == "Box"
    assert envelope["session_token"] == "test-session-token"
    assert isinstance(envelope["operation"]["name"], str) and envelope["operation"]["name"]
    assert headers["X-MCP-Instance-Id"] == "c0deface-1111-4111-8111-000000000001"
    assert transport.closed is True
