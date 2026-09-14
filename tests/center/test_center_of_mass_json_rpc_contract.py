"""Agent-to-FreeCAD wire contract for the ``center_of_mass`` MCP operation."""

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
from freecad_mcp._shared.protocol.center_of_mass_contract import make_center_of_mass_success
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.freecad_client_ops.connection_methods.connection_headers_ops import (
    configure_rpc_session,
)
from freecad_mcp.generated.capabilities.register_modules import tools_measure_b
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
            from tests.center.test_center_of_mass_response import _success
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
    monkeypatch.setattr(tools_measure_b, "server_connection", lambda: connection)
    monkeypatch.setattr(
        tools_measure_b,
        "server_state",
        lambda: SimpleNamespace(only_text_feedback=True),
        raising=False,
    )
    bind_instrumented_fast_mcp(InstrumentedFastMCP)
    mcp = InstrumentedFastMCP("center_of_mass-contract")
    exports = {}
    tools_measure_b._register_center_of_mass(mcp, dependencies=object(), exports=exports)

    async def invoke():
        async with create_connected_server_and_client_session(mcp._mcp_server) as client:
            listing = await client.list_tools()
            tool = next(tool for tool in listing.tools if tool.name == "center_of_mass")
            return await client.call_tool("center_of_mass", arguments)

    try:
        return asyncio.run(invoke())
    finally:
        connection.disconnect()


def test_center_of_mass_sends_authenticated_json_rpc_to_freecad(monkeypatch):
    transport = _RecordingFreeCADTransport()
    arguments = {"doc_name": "AgentDocument"}
    # Fill remaining required tool fields with benign values.
    if "center_of_mass" == "create_assembly_grounded_joint":
        arguments.update({"assembly_name": "Assembly", "component_name": "Base"})
    elif "center_of_mass" == "create_assembly_joint":
        arguments.update({
            "assembly_name": "Assembly",
            "joint_type": "Fixed",
            "ref1_component": "A",
            "ref2_component": "B",
        })
    elif "center_of_mass" == "solve_assembly":
        arguments.update({"assembly_name": "Assembly"})
    elif "center_of_mass" in {"create_helical_gear", "create_involute_gear", "create_spur_gear"}:
        arguments.update({"gear_name": "Gear", "teeth": 8, "module": 2.0, "width": 10.0})
    elif "center_of_mass" == "export_brep":
        arguments.update({"obj_name": "Box", "file_path": "/tmp/out.brep"})
    elif "center_of_mass" in {"export_step", "export_stl"}:
        arguments.update({"file_path": "/tmp/out"})
    elif "center_of_mass" in {"import_brep", "import_step"}:
        arguments.update({"file_path": "/tmp/in"})
    elif "center_of_mass" in {"bounding_box", "center_of_mass"}:
        arguments.update({"obj_name": "Box"})
    elif "center_of_mass" == "common_volume_along_path":
        arguments.update({"moving_object": "Mover", "obstacle_objects": ["Wall"], "samples": [{"x": 0, "y": 0, "z": 0}]})
    elif "center_of_mass" == "rotate":
        arguments.update({"obj_name": "Box", "axis_x": 0, "axis_y": 0, "axis_z": 1, "angle_deg": 90})
    elif "center_of_mass" == "scale":
        arguments.update({"obj_name": "Box", "sx": 1, "sy": 1, "sz": 1})
    elif "center_of_mass" == "translate":
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
    assert envelope["method"] == "center_of_mass"
    assert envelope["params"]["doc_name"] == "AgentDocument"
    assert envelope["session_token"] == "test-session-token"
    assert envelope["operation"]["name"] == "Center of Mass"
    assert headers["X-MCP-Instance-Id"] == "agent-mcp-contract"
    assert transport.closed is True
