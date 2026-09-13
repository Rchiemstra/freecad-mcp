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

    def __init__(self, response_result=None) -> None:
        self.requests: list[tuple[str, dict, dict[str, str]]] = []
        self.extra_headers: list[tuple[str, str]] = []
        self.closed = False
        self.response_result = response_result

    def request(self, path, payload, headers):
        request = json.loads(payload)
        self.requests.append((path, request, dict(headers)))
        envelope = request["params"][0]
        body_result = self.response_result
        if body_result is None:
            body_result = {
                "contract_version": 1,
                "success": True,
                "ok": True,
                "outcome": "committed",
                "committed": True,
                "retry_safe": False,
                "body": envelope["params"]["body_name"],
                "label": envelope["params"]["body_name"],
            }
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


class _CapturingMcp:
    """Expose the function registered by the generated MCP tool wrapper."""

    @staticmethod
    def tool():
        return lambda function: function


def _invoke_registered_body(monkeypatch, transport, doc_name, body_name):
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
        return exports["body_create"](None, doc_name, body_name)
    finally:
        connection.disconnect()


def test_body_create_sends_exact_authenticated_json_rpc_values_to_freecad(
    monkeypatch,
):
    transport = _RecordingFreeCADTransport()
    result = _invoke_registered_body(
        monkeypatch, transport, "AgentDocument", "MainBody"
    )

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


@pytest.mark.parametrize(
    ("body_name", "response_result", "expected_code"),
    [
        (
            "",
            {
                "contract_version": 1,
                "success": False,
                "ok": False,
                "outcome": "rejected",
                "committed": False,
                "retry_safe": True,
                "error_code": "INVALID_ARGUMENT",
                "error": "body_name must be a nonempty string",
            },
            "INVALID_ARGUMENT",
        ),
        (
            "ExistingBody",
            {
                "contract_version": 1,
                "success": False,
                "ok": False,
                "outcome": "rejected",
                "committed": False,
                "retry_safe": True,
                "error_code": "OBJECT_ALREADY_EXISTS",
                "error": "Object already exists",
            },
            "OBJECT_ALREADY_EXISTS",
        ),
    ],
    ids=("invalid-request", "downstream-rejection"),
)
def test_public_body_create_route_never_turns_rejection_into_success(
    monkeypatch,
    body_name,
    response_result,
    expected_code,
):
    transport = _RecordingFreeCADTransport(response_result)

    result = _invoke_registered_body(monkeypatch, transport, "AgentDocument", body_name)

    assert result.isError is True
    assert result.structuredContent["error_code"] == expected_code
    assert result.structuredContent["data"]["committed"] is False
    assert len(transport.requests) == 1


def test_public_route_marks_committed_but_invalid_response_non_retryable(monkeypatch):
    transport = _RecordingFreeCADTransport(
        {
            "contract_version": 1,
            "success": True,
            "ok": True,
            "outcome": "committed",
            "committed": True,
            "retry_safe": False,
            "label": "missing assigned name",
        }
    )

    result = _invoke_registered_body(
        monkeypatch, transport, "AgentDocument", "MainBody"
    )

    assert result.isError is True
    assert (
        result.structuredContent["error_code"]
        == "BODY_CREATE_COMMITTED_RESPONSE_INVALID"
    )
    assert result.structuredContent["data"]["outcome"] == "uncertain"
    assert result.structuredContent["data"]["committed"] is True
    assert result.structuredContent["data"]["retry_safe"] is False
