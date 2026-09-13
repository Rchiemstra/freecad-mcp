"""Agent-to-FreeCAD wire contract for the ``body_create`` MCP operation."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.json_rpc_client import (
    JSON_RPC_HTTP_PATH,
    JSON_RPC_PROTOCOL_HEADER,
    JSON_RPC_PROTOCOL_VALUE,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.freecad_client_ops.connection_methods.connection_headers_ops import (
    configure_rpc_session,
)
from freecad_mcp.generated.capabilities.register_modules import tools_parametric_body
from freecad_mcp.rpc_session import RpcAuthenticationSession

pytestmark = pytest.mark.unit


class _RecordingFreeCADTransport:
    """Capture the JSON document that MCP would POST to FreeCAD."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict, dict[str, str]]] = []
        self.extra_headers: list[tuple[str, str]] = []
        self.closed = False

    def request(self, path, payload, headers):
        request = json.loads(payload)
        self.requests.append((path, request, dict(headers)))
        envelope = request["params"][0]
        response = {
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": {
                "ok": True,
                "request_id": envelope["request_id"],
                "result": {
                    "success": True,
                    "ok": True,
                    "body": envelope["params"]["body_name"],
                    "label": envelope["params"]["body_name"],
                },
            },
        }
        return (
            200,
            {JSON_RPC_PROTOCOL_HEADER.lower(): (JSON_RPC_PROTOCOL_VALUE,)},
            json.dumps(response).encode(),
        )

    def close(self) -> None:
        self.closed = True


class _CapturingMcp:
    """Expose the function registered by the generated MCP tool wrapper."""

    @staticmethod
    def tool():
        return lambda function: function


def test_body_create_sends_exact_authenticated_json_rpc_values_to_freecad(
    monkeypatch,
):
    connection = FreeCADConnection(
        host="127.0.0.1",
        port=9875,
        mcp_instance_id="agent-mcp-contract",
    )
    session = RpcAuthenticationSession()
    session.mark_connected(
        "test-session-token",
        session_id="test-session",
        expires_at="2099-01-01T00:00:00Z",
    )
    configure_rpc_session(connection, session)

    connection.server.transport.close()
    transport = _RecordingFreeCADTransport()
    connection.server.transport = transport
    monkeypatch.setattr(tools_parametric_body, "server_connection", lambda: connection)
    monkeypatch.setattr(
        tools_parametric_body,
        "server_state",
        lambda: SimpleNamespace(only_text_feedback=True),
    )
    exports = {}
    tools_parametric_body._register_body_create(
        _CapturingMcp(),
        dependencies=object(),
        exports=exports,
    )
    try:
        result = exports["body_create"](None, "AgentDocument", "MainBody")
    finally:
        connection.disconnect()

    assert result.isError is False
    assert len(transport.requests) == 1
    path, request, headers = transport.requests[0]
    assert path == JSON_RPC_HTTP_PATH
    assert request["jsonrpc"] == "2.0"
    assert request["method"] == "invoke_v2"
    assert request["id"] == 1
    assert len(request["params"]) == 1

    envelope = request["params"][0]
    uuid.UUID(envelope["request_id"])
    assert envelope == {
        "protocol_version": 2,
        "request_id": envelope["request_id"],
        "session_token": "test-session-token",
        "method": "body_create",
        "params": {
            "doc_name": "AgentDocument",
            "body_name": "MainBody",
        },
        "lease_credentials": [],
        "operation": {"name": "Create Body"},
    }
    assert headers["X-MCP-Instance-Id"] == "agent-mcp-contract"
    assert headers[JSON_RPC_PROTOCOL_HEADER] == JSON_RPC_PROTOCOL_VALUE
    assert transport.closed is True
