from __future__ import annotations

import asyncio
from types import SimpleNamespace
import uuid

import pytest
from mcp.types import CallToolResult

from freecad_mcp.instrumented_server import InstrumentedFastMCP
from freecad_mcp.mcp_tasks import finish, get, link_runtime, register
from freecad_mcp.responses import tool_ok
from freecad_mcp.telemetry.context import get_context


pytestmark = pytest.mark.unit


def test_task_link_maps_existing_request_and_worker_identifiers():
    task_id = str(uuid.uuid4())
    register(task_id, "validate_geometry")
    link_runtime(task_id, request_id="request-id", worker_job_id="worker-id")
    finish(task_id, "completed")
    assert get(task_id) == {
        "task_id": task_id,
        "tool_name": "validate_geometry",
        "request_id": "request-id",
        "worker_job_id": "worker-id",
        "status": "completed",
    }


def _context(experimental):
    return SimpleNamespace(
        request_id="protocol-call",
        request_context=SimpleNamespace(
            meta=None,
            experimental=experimental,
        ),
    )


def _assert_wire_result(actual, expected):
    if isinstance(actual, CallToolResult):
        assert actual is expected
    else:
        assert actual == (expected.content, expected.structuredContent)


def test_call_tool_result_annotation_advertises_envelope_schema():
    server = InstrumentedFastMCP("schema-test")

    @server.tool(name="enveloped")
    def enveloped() -> CallToolResult:
        return tool_ok("value")

    schema = server._tool_manager.get_tool(
        "enveloped"
    ).fn_metadata.output_schema
    assert schema["title"] == "FreeCADMCPResultEnvelope"
    assert schema["properties"]["schema_version"] == {"const": 1}
    assert "condition_false" in schema["properties"]["status"]["enum"]


def test_instrumented_server_keeps_synchronous_fallback(monkeypatch):
    server = InstrumentedFastMCP("task-test")

    @server.tool(name="light_tool")
    def light_tool(value: int):
        return value

    expected = tool_ok("sync")

    async def base_call(_name, _arguments):
        return expected

    monkeypatch.setattr(server, "_call_registered_tool", base_call)
    monkeypatch.setattr(server, "get_context", lambda: _context(None))
    monkeypatch.setattr(
        "freecad_mcp.instrumented_server.emit_event",
        lambda *_args, **_kwargs: None,
    )
    _assert_wire_result(
        asyncio.run(server.call_tool("light_tool", {"value": 1})),
        expected,
    )


def test_instrumented_server_uses_negotiated_task_without_second_job_system(
    monkeypatch,
):
    server = InstrumentedFastMCP("task-test")

    @server.tool(name="validate_geometry")
    def validate_geometry(value: int):
        return value

    expected = tool_ok("task")
    task_id = str(uuid.uuid4())

    async def base_call(_name, _arguments):
        return expected

    class Experimental:
        task_metadata = object()

        async def run_task(self, work, **_kwargs):
            context = SimpleNamespace(
                task=SimpleNamespace(taskId=task_id)
            )
            return await work(context)

    monkeypatch.setattr(server, "_call_registered_tool", base_call)
    monkeypatch.setattr(
        server, "get_context", lambda: _context(Experimental())
    )
    monkeypatch.setattr(
        "freecad_mcp.instrumented_server.emit_event",
        lambda *_args, **_kwargs: None,
    )
    _assert_wire_result(
        asyncio.run(
            server.call_tool("validate_geometry", {"value": 1})
        ),
        expected,
    )
    assert get(task_id)["status"] == "completed"


def test_mcp_task_cancellation_bridges_to_linked_authenticated_request(
    monkeypatch,
):
    server = InstrumentedFastMCP("task-test")

    @server.tool(name="validate_geometry")
    def validate_geometry(value: int):
        return value

    task_id = str(uuid.uuid4())
    cancelled_requests = []

    async def base_call(_name, _arguments):
        link_runtime(get_context().task_id, request_id="linked-request")
        raise asyncio.CancelledError()

    class Experimental:
        task_metadata = object()

        async def run_task(self, work, **_kwargs):
            return await work(
                SimpleNamespace(task=SimpleNamespace(taskId=task_id))
            )

    monkeypatch.setattr(server, "_call_registered_tool", base_call)
    monkeypatch.setattr(
        server, "get_context", lambda: _context(Experimental())
    )
    monkeypatch.setattr(
        "freecad_mcp.instrumented_server.emit_event",
        lambda *_args, **_kwargs: None,
    )
    server.task_request_canceller = cancelled_requests.append
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            server.call_tool("validate_geometry", {"value": 1})
        )
    assert cancelled_requests == ["linked-request"]
    assert get(task_id)["status"] == "cancelled"
