"""Agent-to-FreeCAD wire contract for the ``scale`` MCP operation."""

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
from freecad_mcp._shared.protocol.scale_contract import make_scale_success
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.freecad_client_ops.connection_methods.connection_headers_ops import (
    configure_rpc_session,
)
from freecad_mcp.generated.capabilities.register_modules import tools_transform
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
            from tests.test_scale_response import _success
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
    monkeypatch.setattr(tools_transform, "server_connection", lambda: connection)
    monkeypatch.setattr(
        tools_transform,
        "server_state",
        lambda: SimpleNamespace(only_text_feedback=True),
        raising=False,
    )
    bind_instrumented_fast_mcp(InstrumentedFastMCP)
    mcp = InstrumentedFastMCP("scale-contract")
    exports = {}
    tools_transform._register_scale(mcp, dependencies=object(), exports=exports)

    async def invoke():
        async with create_connected_server_and_client_session(mcp._mcp_server) as client:
            listing = await client.list_tools()
            tool = next(tool for tool in listing.tools if tool.name == "scale")
            return await client.call_tool("scale", arguments)

    try:
        return asyncio.run(invoke())
    finally:
        connection.disconnect()


def test_scale_sends_authenticated_json_rpc_to_freecad(monkeypatch):
    transport = _RecordingFreeCADTransport()
    arguments = {"doc_name": "AgentDocument"}
    # Fill remaining required tool fields with benign values.
    if "scale" == "create_assembly_grounded_joint":
        arguments.update({"assembly_name": "Assembly", "component_name": "Base"})
    elif "scale" == "create_assembly_joint":
        arguments.update({
            "assembly_name": "Assembly",
            "joint_type": "Fixed",
            "ref1_component": "A",
            "ref2_component": "B",
        })
    elif "scale" == "solve_assembly":
        arguments.update({"assembly_name": "Assembly"})
    elif "scale" in {"create_helical_gear", "create_involute_gear", "create_spur_gear"}:
        arguments.update({"gear_name": "Gear", "teeth": 8, "module": 2.0, "width": 10.0})
    elif "scale" == "export_brep":
        arguments.update({"obj_name": "Box", "file_path": "/tmp/out.brep"})
    elif "scale" in {"export_step", "export_stl"}:
        arguments.update({"file_path": "/tmp/out"})
    elif "scale" in {"import_brep", "import_step"}:
        arguments.update({"file_path": "/tmp/in"})
    elif "scale" in {"bounding_box", "center_of_mass"}:
        arguments.update({"obj_name": "Box"})
    elif "scale" == "common_volume_along_path":
        arguments.update({"moving_object": "Mover", "obstacle_objects": ["Wall"], "samples": [{"x": 0, "y": 0, "z": 0}]})
    elif "scale" == "rotate":
        arguments.update({"obj_name": "Box", "axis_x": 0, "axis_y": 0, "axis_z": 1, "angle_deg": 90})
    elif "scale" == "scale":
        arguments.update({"obj_name": "Box", "sx": 1, "sy": 1, "sz": 1})
    elif "scale" == "translate":
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
    assert envelope["method"] == "scale"
    assert envelope["params"]["doc_name"] == "AgentDocument"
    assert envelope["session_token"] == "test-session-token"
    assert envelope["operation"]["name"] == "Scale"
    assert headers["X-MCP-Instance-Id"] == "agent-mcp-contract"
    assert transport.closed is True
