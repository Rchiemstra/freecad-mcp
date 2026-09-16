"""Agent-to-FreeCAD wire contract for the ``build_path_wire`` MCP operation."""

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
from freecad_mcp.generated.capabilities.register_modules import tools_partdesign_a2
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
            body_result = dict({"contract_version": 1, "success": True, "ok": True, "outcome": "committed", "committed": True, "retry_safe": False, "wire_name": "Value"}, **{
                key: envelope["params"][key]
                for key in envelope["params"]
                if key in ['wire_name']
            })
            body_result = {"contract_version": 1, "success": True, "ok": True, "outcome": "committed", "committed": True, "retry_safe": False, "wire_name": "Value"}
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
    connection = FreeCADConnection(host="127.0.0.1", port=9875, mcp_instance_id="c0deface-1111-4111-8111-000000000001")
    session = RpcAuthenticationSession()
    session.mark_connected("test-session-token", session_id="test-session", expires_at="2099-01-01T00:00:00Z")
    configure_rpc_session(connection, session)
    connection.server.transport.close()
    connection.server.transport = transport
    monkeypatch.setattr(tools_partdesign_a2, "server_connection", lambda: connection)
    monkeypatch.setattr(tools_partdesign_a2, "server_state", lambda: SimpleNamespace(only_text_feedback=True))
    bind_instrumented_fast_mcp(InstrumentedFastMCP)
    mcp = InstrumentedFastMCP("build_path_wire-contract")
    exports = {}
    tools_partdesign_a2._register_build_path_wire(mcp, dependencies=object(), exports=exports)

    async def invoke():
        async with create_connected_server_and_client_session(mcp._mcp_server) as client:
            listing = await client.list_tools()
            tool = next(tool for tool in listing.tools if tool.name == "build_path_wire")
            required = tool.inputSchema.get("required") or []
            assert "doc_name" in required
            return await client.call_tool("build_path_wire", params)

    try:
        return asyncio.run(invoke())
    finally:
        connection.disconnect()


def test_build_path_wire_sends_authenticated_json_rpc_to_freecad(monkeypatch):
    transport = _RecordingFreeCADTransport()
    result = _invoke_registered(monkeypatch, transport, {"doc_name": "AgentDocument", "wire_name": "Value", "segments": [{"sketch": "Seed", "geo_index": 0}], "tolerance_mm": 1.0, "if_exists": "error"})
    assert result.isError is False
    assert len(transport.requests) == 1
    path, request, headers = transport.requests[0]
    assert path == JSON_RPC_HTTP_PATH
    assert request["jsonrpc"] == "2.0"
    assert request["method"] == "invoke_v2"
    envelope = request["params"][0]
    uuid.UUID(envelope["request_id"])
    assert envelope["method"] == "build_path_wire"
    assert envelope["params"]["doc_name"] == "AgentDocument"
    assert headers["X-MCP-Instance-Id"] == "c0deface-1111-4111-8111-000000000001"
    assert headers[JSON_RPC_PROTOCOL_HEADER] == JSON_RPC_PROTOCOL_VALUE
    assert transport.closed is True


def test_mcp_schema_rejects_non_string_doc_name_before_json_rpc(monkeypatch):
    transport = _RecordingFreeCADTransport()
    params = dict({"doc_name": "AgentDocument", "wire_name": "Value", "segments": [{"sketch": "Seed", "geo_index": 0}], "tolerance_mm": 1.0, "if_exists": "error"})
    params["doc_name"] = 42
    result = _invoke_registered(monkeypatch, transport, params)
    assert result.isError is True
    assert transport.requests == []
