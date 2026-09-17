"""Mocked authenticated RPC v2 recovery/control surface (unit scope).

Native GUI x3 recovery is blocked without a FreeCAD binary in this worktree.
"""

from __future__ import annotations

import json

import pytest

from freecad_mcp._shared.protocol.json_rpc_client import (
    JSON_RPC_PROTOCOL_HEADER,
    JSON_RPC_PROTOCOL_VALUE,
)
from freecad_mcp._shared.protocol.undo_contract import make_undo_success
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.freecad_client_ops.connection_methods.connection_headers_ops import (
    configure_rpc_session,
)
from freecad_mcp.generated.capabilities.connection_methods.connection_control_ops import (
    cancel_request,
    get_request_status,
)
from freecad_mcp.generated.capabilities.connection_methods.connection_model_ops import (
    redo,
    undo,
)
from freecad_mcp.generated.capabilities.connection_methods.connection_save_ops import (
    save_document,
)
from freecad_mcp.generated.capabilities.connection_methods.connection_view_ops import (
    open_document,
)
from freecad_mcp.rpc_session import RpcAuthenticationSession
from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

pytestmark = pytest.mark.unit

_DEFAULT_RESPONSE = object()
_AUTH_REQUIRED = "requires authenticated RPC v2"
_REQUEST_ID = "00000000-0000-4000-8000-000000000001"


def _readiness(doc_name: str = "AgentDocument") -> dict:
    name = doc_name or "AgentDocument"
    return {
        "success": True,
        "ready": True,
        "documents": [
            {
                "document": name,
                "ready": True,
                "document_uid": "uid-doc-1",
                "document_instance_id": 7,
                "lifecycle_epoch": 2,
                "document_name": name,
                "undo_count": 3,
                "undo_head": "EditSketch",
                "redo_count": 1,
                "redo_head": "Pad",
            }
        ],
        "reasons": [],
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
            params = envelope["params"]
            if envelope["method"] == "undo" or envelope["method"] == "redo":
                document_name = params.get("doc_selector", {}).get("document_name", "AgentDocument")
                body_result = make_undo_success(document_name)
            else:
                body_result = {
                    "contract_version": 1,
                    "success": True,
                    "ok": True,
                    "outcome": "verified",
                    "retry_safe": False,
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


def _wire_transport(connection: FreeCADConnection, transport: _RecordingFreeCADTransport) -> None:
    for lane_name in ("server", "control_server"):
        lane = getattr(connection, lane_name, None)
        if lane is not None and getattr(lane, "transport", None) is not None:
            lane.transport.close()
            lane.transport = transport


def _authenticated_connection(transport: _RecordingFreeCADTransport) -> FreeCADConnection:
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
    _wire_transport(connection, transport)
    connection.server.get_mutation_readiness = lambda doc_name=None: _readiness(
        doc_name or "AgentDocument"
    )
    return connection


def _unauthenticated_connection() -> FreeCADConnection:
    return FreeCADConnection(
        host="127.0.0.1",
        port=9875,
        mcp_instance_id="c0deface-1111-4111-8111-000000000002",
    )


@pytest.fixture(autouse=True)
def _bootstrap():
    bootstrap_unit_test_runtime()


def test_authenticated_session_routes_v2_recovery_controls() -> None:
    transport = _RecordingFreeCADTransport()
    connection = _authenticated_connection(transport)

    assert get_request_status(connection, _REQUEST_ID)["success"] is True
    assert cancel_request(connection, _REQUEST_ID)["success"] is True
    assert save_document(connection, {"document_name": "Demo"})["success"] is True
    assert open_document(connection, "C:/models/part.FCStd")["success"] is True
    assert undo(connection, "AgentDocument")["success"] is True
    assert redo(connection, "AgentDocument")["success"] is True
    assert len(transport.requests) == 6
    for _, request, _ in transport.requests:
        assert request["method"] in {"invoke_v2", "invoke_v2_control"}
        assert request["params"][0]["session_token"] == "test-session-token"
    connection.disconnect()


def test_unauthenticated_control_operations_are_refused() -> None:
    connection = _unauthenticated_connection()

    for result in (
        get_request_status(connection, _REQUEST_ID),
        cancel_request(connection, _REQUEST_ID),
    ):
        assert result["success"] is False
        assert _AUTH_REQUIRED in result["error"]

    connection.disconnect()


def test_unauthenticated_document_mutations_do_not_require_v2_auth_error() -> None:
    connection = _unauthenticated_connection()

    assert open_document(connection, "C:/models/part.FCStd")["error_code"] == "LEASE_PROTOCOL_REQUIRED"
    assert _AUTH_REQUIRED not in open_document(connection, "C:/models/part.FCStd")["error"]

    connection.disconnect()
