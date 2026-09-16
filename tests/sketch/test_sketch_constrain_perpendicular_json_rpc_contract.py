"""Agent-to-FreeCAD wire contract for the ``sketch_constrain_perpendicular`` MCP operation."""

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
from freecad_mcp.generated.capabilities.register_modules import tools_sketch_constraints_2
from freecad_mcp.instrumented_server import InstrumentedFastMCP
from freecad_mcp.instrumented_server_ops.facade_bindings import bind_instrumented_fast_mcp
from freecad_mcp.rpc_session import RpcAuthenticationSession

pytestmark = pytest.mark.unit
_DEFAULT_RESPONSE = object()
_TOOL_PARAMS = {'doc_name': 'AgentDocument', 'sketch_name': 'Sketch', 'geo1': 0, 'geo2': 1}


class _RecordingFreeCADTransport:
    def __init__(self, response_result=_DEFAULT_RESPONSE) -> None:
        self.requests: list[tuple[str, dict, dict[str, str]]] = []
        self.closed = False
        self.response_result = response_result

    def request(self, path, payload, headers):
        request = json.loads(payload)
        self.requests.append((path, request, dict(headers)))
        envelope = request["params"][0]
        result = self.response_result
        if result is _DEFAULT_RESPONSE:
            result = {
                "contract_version": 1,
                "success": True,
                "ok": True,
                "outcome": "committed",
                "committed": True,
                "retry_safe": False,
                "sketch": envelope["params"]["sketch_name"],
                "constraint_index": 0,
            }
        response = {
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": {
                "ok": True,
                "request_id": envelope["request_id"],
                "result": result,
            },
        }
        return (
            200,
            {JSON_RPC_PROTOCOL_HEADER.lower(): (JSON_RPC_PROTOCOL_VALUE,)},
            json.dumps(response).encode(),
        )

    def close(self) -> None:
        self.closed = True


def _invoke_registered(monkeypatch, transport, arguments):
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
    monkeypatch.setattr(tools_sketch_constraints_2, "server_connection", lambda: connection)
    monkeypatch.setattr(
        tools_sketch_constraints_2,
        "server_state",
        lambda: SimpleNamespace(only_text_feedback=True),
    )
    bind_instrumented_fast_mcp(InstrumentedFastMCP)
    mcp = InstrumentedFastMCP("sketch_constrain_perpendicular-contract")
    exports = {}
    tools_sketch_constraints_2._register_sketch_constrain_perpendicular(mcp, dependencies=object(), exports=exports)

    async def invoke():
        async with create_connected_server_and_client_session(mcp._mcp_server) as client:
            listing = await client.list_tools()
            tool = next(tool for tool in listing.tools if tool.name == "sketch_constrain_perpendicular")
            assert set(tool.inputSchema["required"]) == {'doc_name', 'geo1', 'sketch_name', 'geo2'}
            return await client.call_tool("sketch_constrain_perpendicular", arguments)

    try:
        return asyncio.run(invoke())
    finally:
        connection.disconnect()


def test_sketch_constrain_perpendicular_sends_exact_authenticated_json_rpc_values_to_freecad(monkeypatch):
    transport = _RecordingFreeCADTransport()
    result = _invoke_registered(monkeypatch, transport, dict(_TOOL_PARAMS))

    assert result.isError is False
    assert len(transport.requests) == 1
    path, request, headers = transport.requests[0]
    assert path == JSON_RPC_HTTP_PATH
    assert request["jsonrpc"] == "2.0"
    assert request["method"] == "invoke_v2"
    envelope = request["params"][0]
    uuid.UUID(envelope["request_id"])
    assert envelope["method"] == "sketch_constrain_perpendicular"
    assert envelope["params"]["doc_name"] == "AgentDocument"
    assert envelope["params"]["sketch_name"] == "Sketch"
    assert headers["X-MCP-Instance-Id"] == "c0deface-1111-4111-8111-000000000001"
    assert transport.closed is True


def test_public_route_never_turns_rejection_into_success(monkeypatch):
    transport = _RecordingFreeCADTransport(
        {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "rejected",
            "committed": False,
            "retry_safe": True,
            "error_code": "INVALID_ARGUMENT",
            "error": "rejected",
        }
    )
    result = _invoke_registered(monkeypatch, transport, dict(_TOOL_PARAMS))
    assert result.isError is True
    assert result.structuredContent["error_code"] == "INVALID_ARGUMENT"
    assert result.structuredContent["data"]["committed"] is False


def test_public_route_marks_committed_but_invalid_response_non_retryable(monkeypatch):
    transport = _RecordingFreeCADTransport(
        {
            "contract_version": 1,
            "success": True,
            "ok": True,
            "outcome": "committed",
            "committed": True,
            "retry_safe": False,
        }
    )
    result = _invoke_registered(monkeypatch, transport, dict(_TOOL_PARAMS))
    assert result.isError is True
    assert result.structuredContent["data"]["outcome"] == "uncertain"
    assert result.structuredContent["data"]["retry_safe"] is False


@pytest.mark.parametrize("doc_name", [None, 42, [], {}])
def test_mcp_schema_rejects_non_string_before_json_rpc(monkeypatch, doc_name):
    transport = _RecordingFreeCADTransport()
    payload = dict(_TOOL_PARAMS)
    payload["doc_name"] = doc_name
    result = _invoke_registered(monkeypatch, transport, payload)
    assert result.isError is True
    assert transport.requests == []
