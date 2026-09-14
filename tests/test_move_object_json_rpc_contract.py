"""Agent-to-FreeCAD wire contract for the ``move_object`` MCP operation."""

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
from freecad_mcp.generated.capabilities.register_modules import tools_partdesign_a
from freecad_mcp.instrumented_server import InstrumentedFastMCP
from freecad_mcp.instrumented_server_ops.facade_bindings import bind_instrumented_fast_mcp
from freecad_mcp.rpc_session import RpcAuthenticationSession

pytestmark = pytest.mark.unit
_DEFAULT_RESPONSE = object()


class _RecordingFreeCADTransport:
    def __init__(self, response_result=_DEFAULT_RESPONSE) -> None:
        self.requests: list[tuple[str, dict, dict[str, str]]] = []
        self.extra_headers: list[tuple[str, str]] = []
        self.closed = False
        self.response_result = response_result

    def request(self, path, payload, headers):
        request = json.loads(payload)
        self.requests.append((path, request, dict(headers)))
        envelope = request["params"][0]
        body_result = self.response_result
        if body_result is _DEFAULT_RESPONSE:
            body_result = dict({"contract_version": 1, "success": True, "ok": True, "outcome": "committed", "committed": True, "retry_safe": False, "object_name": "Value", "target_container": "Value"}, **{
                key: envelope["params"][key]
                for key in envelope["params"]
                if key in ['object_name', 'target_container']
            })
            body_result = {"contract_version": 1, "success": True, "ok": True, "outcome": "committed", "committed": True, "retry_safe": False, "object_name": "Value", "target_container": "Value"}
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


def _invoke_registered(monkeypatch, transport, params):
    connection = FreeCADConnection(host="127.0.0.1", port=9875, mcp_instance_id="agent-mcp-contract")
    session = RpcAuthenticationSession()
    session.mark_connected("test-session-token", session_id="test-session", expires_at="2099-01-01T00:00:00Z")
    configure_rpc_session(connection, session)
    connection.server.transport.close()
    connection.server.transport = transport
    monkeypatch.setattr(tools_partdesign_a, "server_connection", lambda: connection)
    monkeypatch.setattr(tools_partdesign_a, "server_state", lambda: SimpleNamespace(only_text_feedback=True))
    bind_instrumented_fast_mcp(InstrumentedFastMCP)
    mcp = InstrumentedFastMCP("move_object-contract")
    exports = {}
    tools_partdesign_a._register_move_object(mcp, dependencies=object(), exports=exports)

    async def invoke():
        async with create_connected_server_and_client_session(mcp._mcp_server) as client:
            listing = await client.list_tools()
            tool = next(tool for tool in listing.tools if tool.name == "move_object")
            assert "doc_name" in tool.inputSchema.get("required", ["doc_name"])
            return await client.call_tool("move_object", params)

    try:
        return asyncio.run(invoke())
    finally:
        connection.disconnect()


def test_move_object_sends_authenticated_json_rpc_to_freecad(monkeypatch):
    transport = _RecordingFreeCADTransport()
    result = _invoke_registered(monkeypatch, transport, {"doc_name": "AgentDocument", "obj_name": "Value", "target_container": "Value", "remove_from_old_parent": True})
    assert result.isError is False or result.structuredContent["data"]["outcome"] in {"committed", "rejected", "uncertain"}
    assert len(transport.requests) == 1
    path, request, headers = transport.requests[0]
    assert path == JSON_RPC_HTTP_PATH
    assert request["jsonrpc"] == "2.0"
    assert request["method"] == "invoke_v2"
    envelope = request["params"][0]
    uuid.UUID(envelope["request_id"])
    assert envelope["method"] == "move_object"
    assert envelope["params"]["doc_name"] == "AgentDocument"
    assert headers["X-MCP-Instance-Id"] == "agent-mcp-contract"
    assert headers[JSON_RPC_PROTOCOL_HEADER] == JSON_RPC_PROTOCOL_VALUE
    assert transport.closed is True


def test_mcp_schema_rejects_non_string_doc_name_before_json_rpc(monkeypatch):
    transport = _RecordingFreeCADTransport()
    params = dict({"doc_name": "AgentDocument", "obj_name": "Value", "target_container": "Value", "remove_from_old_parent": True})
    params["doc_name"] = 42
    result = _invoke_registered(monkeypatch, transport, params)
    assert result.isError is True
    assert transport.requests == []
