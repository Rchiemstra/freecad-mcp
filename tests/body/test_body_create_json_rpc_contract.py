"""Agent-to-FreeCAD wire contract for the ``body_create`` MCP operation."""

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
from freecad_mcp.generated.capabilities.register_modules import tools_parametric_body
from freecad_mcp.instrumented_server import InstrumentedFastMCP
from freecad_mcp.instrumented_server_ops.facade_bindings import bind_instrumented_fast_mcp
from freecad_mcp.rpc_session import RpcAuthenticationSession

pytestmark = pytest.mark.unit
_DEFAULT_RESPONSE = object()


class _RecordingFreeCADTransport:
    """Capture the JSON document that MCP would POST to FreeCAD."""

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


def _invoke_registered_body(monkeypatch, transport, doc_name, body_name):
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
    monkeypatch.setattr(tools_parametric_body, "server_connection", lambda: connection)
    monkeypatch.setattr(
        tools_parametric_body,
        "server_state",
        lambda: SimpleNamespace(only_text_feedback=True),
    )
    bind_instrumented_fast_mcp(InstrumentedFastMCP)
    mcp = InstrumentedFastMCP("body-create-contract")
    exports = {}
    tools_parametric_body._register_body_create(
        mcp,
        dependencies=object(),
        exports=exports,
    )

    async def invoke():
        async with create_connected_server_and_client_session(mcp._mcp_server) as client:
            listing = await client.list_tools()
            tool = next(tool for tool in listing.tools if tool.name == "body_create")
            assert set(tool.inputSchema["required"]) == {"doc_name", "body_name"}
            assert tool.inputSchema["properties"]["doc_name"]["type"] == "string"
            assert tool.inputSchema["properties"]["body_name"]["type"] == "string"
            return await client.call_tool(
                "body_create", {"doc_name": doc_name, "body_name": body_name}
            )

    try:
        return asyncio.run(invoke())
    finally:
        connection.disconnect()


def test_body_create_sends_exact_authenticated_json_rpc_values_to_freecad(
    monkeypatch,
):
    transport = _RecordingFreeCADTransport()
    result = _invoke_registered_body(monkeypatch, transport, "AgentDocument", "MainBody")

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
        "mcp_runtime_id": "c0deface-1111-4111-8111-000000000001",
        "method": "body_create",
        "params": {
            "doc_name": "AgentDocument",
            "body_name": "MainBody",
        },
        "lease_credentials": [],
        "operation": {"name": "Create Body"},
    }
    assert headers["X-MCP-Instance-Id"] == "c0deface-1111-4111-8111-000000000001"
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

    result = _invoke_registered_body(monkeypatch, transport, "AgentDocument", "MainBody")

    assert result.isError is True
    assert result.structuredContent["error_code"] == "BODY_CREATE_COMMITTED_RESPONSE_INVALID"
    assert result.structuredContent["data"]["outcome"] == "uncertain"
    assert result.structuredContent["data"]["committed"] is True
    assert result.structuredContent["data"]["retry_safe"] is False


@pytest.mark.parametrize("body_name", [None, 42, [], {}])
def test_mcp_schema_rejects_non_string_before_json_rpc(monkeypatch, body_name):
    transport = _RecordingFreeCADTransport()
    result = _invoke_registered_body(monkeypatch, transport, "Doc", body_name)
    assert result.isError is True
    assert transport.requests == []


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        [],
        {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "STATE_UNKNOWN",
            "error": "Reconcile",
        },
        {
            "contract_version": 1,
            "success": True,
            "ok": True,
            "outcome": "committed",
            "committed": True,
            "retry_safe": False,
            "body": "Body",
            "label": "Body",
            "rollback_failed": True,
        },
        {
            "contract_version": 1,
            "success": True,
            "ok": True,
            "outcome": "committed",
            "committed": True,
            "retry_safe": False,
            "body": "Body",
            "label": "Body",
            "native_status": "Rejected",
        },
    ],
)
def test_mcp_dispatch_preserves_uncertainty_and_error_flag(monkeypatch, payload):
    transport = _RecordingFreeCADTransport(payload)
    result = _invoke_registered_body(monkeypatch, transport, "Doc", "Body")
    assert result.isError is True
    assert result.structuredContent["data"]["outcome"] == "uncertain"
    assert result.structuredContent["data"]["retry_safe"] is False
    assert len(transport.requests) == 1
