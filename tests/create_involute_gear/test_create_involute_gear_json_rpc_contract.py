"""Agent-to-FreeCAD wire contract for the ``create_involute_gear`` MCP operation."""

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
from freecad_mcp._shared.protocol.create_involute_gear_contract import make_create_involute_gear_success
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.freecad_client_ops.connection_methods.connection_headers_ops import (
    configure_rpc_session,
)
from freecad_mcp.generated.capabilities.register_modules import tools_gear_1
from freecad_mcp.instrumented_server import InstrumentedFastMCP
from freecad_mcp.instrumented_server_ops.facade_bindings import bind_instrumented_fast_mcp
from freecad_mcp.rpc_session import RpcAuthenticationSession

pytestmark = pytest.mark.unit
_DEFAULT_RESPONSE = object()


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
            from tests.create_involute_gear.test_create_involute_gear_response import _success
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
    monkeypatch.setattr(tools_gear_1, "server_connection", lambda: connection)
    monkeypatch.setattr(
        tools_gear_1,
        "server_state",
        lambda: SimpleNamespace(only_text_feedback=True),
        raising=False,
    )
    bind_instrumented_fast_mcp(InstrumentedFastMCP)
    mcp = InstrumentedFastMCP("create_involute_gear-contract")
    exports = {}
    tools_gear_1._register_create_involute_gear(mcp, dependencies=object(), exports=exports)

    async def invoke():
        async with create_connected_server_and_client_session(mcp._mcp_server) as client:
            listing = await client.list_tools()
            tool = next(tool for tool in listing.tools if tool.name == "create_involute_gear")
            return await client.call_tool("create_involute_gear", arguments)

    try:
        return asyncio.run(invoke())
    finally:
        connection.disconnect()


def test_create_involute_gear_sends_authenticated_json_rpc_to_freecad(monkeypatch):
    transport = _RecordingFreeCADTransport()
    arguments = {"doc_name": "AgentDocument"}
    # Fill remaining required tool fields with benign values.
    if "create_involute_gear" == "create_assembly_grounded_joint":
        arguments.update({"assembly_name": "Assembly", "component_name": "Base"})
    elif "create_involute_gear" == "create_assembly_joint":
        arguments.update({
            "assembly_name": "Assembly",
            "joint_type": "Fixed",
            "ref1_component": "A",
            "ref2_component": "B",
        })
    elif "create_involute_gear" == "solve_assembly":
        arguments.update({"assembly_name": "Assembly"})
    elif "create_involute_gear" in {"create_helical_gear", "create_involute_gear", "create_spur_gear"}:
        arguments.update({"gear_name": "Gear", "teeth": 8, "module": 2.0, "width": 10.0})
    elif "create_involute_gear" == "export_brep":
        arguments.update({"obj_name": "Box", "file_path": "/tmp/out.brep"})
    elif "create_involute_gear" in {"export_step", "export_stl"}:
        arguments.update({"file_path": "/tmp/out"})
    elif "create_involute_gear" in {"import_brep", "import_step"}:
        arguments.update({"file_path": "/tmp/in"})
    elif "create_involute_gear" in {"bounding_box", "center_of_mass"}:
        arguments.update({"obj_name": "Box"})
    elif "create_involute_gear" == "common_volume_along_path":
        arguments.update({"moving_object": "Mover", "obstacle_objects": ["Wall"], "samples": [{"x": 0, "y": 0, "z": 0}]})
    elif "create_involute_gear" == "rotate":
        arguments.update({"obj_name": "Box", "axis_x": 0, "axis_y": 0, "axis_z": 1, "angle_deg": 90})
    elif "create_involute_gear" == "scale":
        arguments.update({"obj_name": "Box", "sx": 1, "sy": 1, "sz": 1})
    elif "create_involute_gear" == "translate":
        arguments.update({"obj_name": "Box", "dx": 1, "dy": 0, "dz": 0})
    result = _invoke(monkeypatch, transport, arguments)
    assert result.isError is False
    assert len(transport.requests) == 1
    path, request, headers = transport.requests[0]
    assert path == JSON_RPC_HTTP_PATH
    assert request["jsonrpc"] == "2.0"
    assert request["method"] == "invoke_v2"
    envelope = request["params"][0]
    uuid.UUID(envelope["request_id"])
    assert envelope["method"] == "create_involute_gear"
    assert envelope["params"]["doc_name"] == "AgentDocument"
    assert envelope["session_token"] == "test-session-token"
    assert envelope["operation"]["name"] == "Create Involute Gear"
    assert headers["X-MCP-Instance-Id"] == "c0deface-1111-4111-8111-000000000001"
    assert transport.closed is True
