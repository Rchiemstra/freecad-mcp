from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from freecad_mcp import server
from freecad_mcp.instrumented_server import (
    CONTROL_LANE_TOOLS,
    InstrumentedFastMCP,
)
from freecad_mcp.telemetry.context import get_context, update_context

pytestmark = pytest.mark.unit


def _context():
    return SimpleNamespace(
        request_id="protocol-call",
        request_context=SimpleNamespace(meta=None, experimental=None),
    )


def _silence_telemetry(monkeypatch) -> None:
    monkeypatch.setattr(
        "freecad_mcp.instrumented_server.emit_event",
        lambda *_args, **_kwargs: None,
    )


def _registered_mcp_tool_names() -> set[str]:
    manager = getattr(server.mcp, "_tool_manager", None)
    assert manager is not None
    registry = getattr(manager, "_tools", None) or getattr(manager, "tools", None)
    assert isinstance(registry, dict)
    return set(registry)


def test_event_loop_progresses_while_sync_tool_blocks_worker(monkeypatch):
    """Async control work progresses while a sync tool occupies its worker."""

    server_instance = InstrumentedFastMCP("worker-event-loop-test")
    started = threading.Event()
    release = threading.Event()
    progress_ticks: list[float] = []
    probe_interval_s = 0.05

    @server_instance.tool(name="slow_sync_probe")
    def slow_sync_probe() -> dict[str, str]:
        started.set()
        if not release.wait(timeout=5.0):
            raise TimeoutError("slow_sync_probe was not released")
        return {"status": "done"}

    async def progress_loop() -> None:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if started.is_set():
                progress_ticks.append(time.monotonic())
            await asyncio.sleep(probe_interval_s)

    async def wait_for_started() -> None:
        deadline = time.monotonic() + 2.0
        while not started.is_set():
            if time.monotonic() >= deadline:
                raise TimeoutError("slow_sync_probe did not start")
            await asyncio.sleep(0.01)

    async def run() -> None:
        _silence_telemetry(monkeypatch)
        monkeypatch.setattr(server_instance, "get_context", lambda: _context())

        tool_task = asyncio.create_task(
            server_instance.call_tool("slow_sync_probe", {})
        )
        progress_task = asyncio.create_task(progress_loop())

        try:
            await wait_for_started()
            await asyncio.sleep(probe_interval_s * 3)
            assert len(progress_ticks) >= 2, (
                "expected multiple event-loop ticks while sync tool blocked "
                "its worker"
            )
        finally:
            release.set()
            await asyncio.wait_for(tool_task, timeout=5.0)
            progress_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await progress_task

    asyncio.run(run())


def test_sync_tool_runs_off_event_loop_thread(monkeypatch):
    server_instance = InstrumentedFastMCP("worker-thread-test")
    observed: dict[str, int] = {}

    @server_instance.tool(name="thread_probe")
    def thread_probe() -> dict[str, str]:
        observed["worker_thread"] = threading.get_ident()
        return {"status": "done"}

    async def run() -> None:
        observed["loop_thread"] = threading.get_ident()
        await server_instance.call_tool("thread_probe", {})

    _silence_telemetry(monkeypatch)
    monkeypatch.setattr(server_instance, "get_context", lambda: _context())
    asyncio.run(run())

    assert observed["worker_thread"] != observed["loop_thread"]


def test_control_lane_does_not_queue_behind_long_sync_tool(monkeypatch):
    server_instance = InstrumentedFastMCP("worker-control-lane-test")
    general_started = threading.Event()
    general_release = threading.Event()
    lane_threads: dict[str, str] = {}

    @server_instance.tool(name="long_execute_code")
    def long_execute_code() -> dict[str, str]:
        lane_threads["general"] = threading.current_thread().name
        general_started.set()
        if not general_release.wait(timeout=5.0):
            raise TimeoutError("long_execute_code was not released")
        return {"status": "done"}

    @server_instance.tool(name="cancel_request")
    def cancel_request(request_id: str) -> dict[str, str]:
        lane_threads["control"] = threading.current_thread().name
        return {"status": "cancelled", "request_id": request_id}

    async def run() -> None:
        _silence_telemetry(monkeypatch)
        monkeypatch.setattr(server_instance, "get_context", lambda: _context())

        general_task = asyncio.create_task(
            server_instance.call_tool("long_execute_code", {})
        )
        deadline = time.monotonic() + 2.0
        while not general_started.is_set():
            if time.monotonic() >= deadline:
                raise TimeoutError("long_execute_code did not start")
            await asyncio.sleep(0.01)

        cancel_started = time.monotonic()
        cancel_result = await asyncio.wait_for(
            server_instance.call_tool(
                "cancel_request",
                {"request_id": "00000000-0000-4000-8000-000000000001"},
            ),
            timeout=1.0,
        )
        cancel_elapsed = time.monotonic() - cancel_started

        assert cancel_result is not None
        assert "control" in lane_threads, (
            "cancel_request should have run on the control lane"
        )
        assert lane_threads["control"].startswith("mcp-control-tool")
        assert lane_threads["general"].startswith("mcp-sync-tool")
        assert lane_threads["control"] != lane_threads["general"]
        assert cancel_elapsed < 0.5, (
            "control-lane tool should not wait behind the general worker"
        )

        general_release.set()
        await asyncio.wait_for(general_task, timeout=5.0)

    asyncio.run(run())


def test_contextvars_propagate_into_sync_worker(monkeypatch):
    server_instance = InstrumentedFastMCP("worker-context-test")
    observed: dict[str, str] = {}

    @server_instance.tool(name="context_probe")
    def context_probe() -> dict[str, str]:
        observed["call_id"] = get_context().call_id
        observed["operation"] = get_context().operation
        return {"call_id": observed["call_id"]}

    async def invoke() -> None:
        await server_instance.call_tool("context_probe", {})

    _silence_telemetry(monkeypatch)
    monkeypatch.setattr(server_instance, "get_context", lambda: _context())
    asyncio.run(invoke())
    assert observed == {
        "call_id": "protocol-call",
        "operation": "context_probe",
    }


def test_sync_worker_context_updates_merge_back_to_event_loop(monkeypatch):
    server_instance = InstrumentedFastMCP("worker-context-writeback-test")
    completed_context: dict[str, str] = {}

    @server_instance.tool(name="context_writer")
    def context_writer() -> dict[str, str]:
        update_context(
            request_id="worker-request-id",
            execution_id="worker-execution-id",
            worker_job_id="worker-job-id",
        )
        return {"status": "done"}

    def capture_emit(stage, event, **_kwargs) -> None:
        if stage == "mcp" and event == "tool_call_completed":
            ctx = get_context()
            completed_context["request_id"] = ctx.request_id
            completed_context["execution_id"] = ctx.execution_id
            completed_context["worker_job_id"] = ctx.worker_job_id

    async def invoke() -> None:
        await server_instance.call_tool("context_writer", {})

    monkeypatch.setattr(
        "freecad_mcp.instrumented_server.emit_event",
        capture_emit,
    )
    monkeypatch.setattr(server_instance, "get_context", lambda: _context())
    asyncio.run(invoke())

    assert completed_context == {
        "request_id": "worker-request-id",
        "execution_id": "worker-execution-id",
        "worker_job_id": "worker-job-id",
    }


def test_sync_worker_context_updates_merge_back_on_tool_failure(monkeypatch):
    server_instance = InstrumentedFastMCP("worker-context-failure-writeback-test")
    failed_context: dict[str, str] = {}

    @server_instance.tool(name="context_writer_failing")
    def context_writer_failing() -> dict[str, str]:
        update_context(
            request_id="worker-request-id",
            execution_id="worker-execution-id",
            worker_job_id="worker-job-id",
        )
        raise ToolError("tool failed after context update")

    def capture_emit(stage, event, **_kwargs) -> None:
        if stage == "mcp" and event == "tool_call_completed":
            ctx = get_context()
            failed_context["request_id"] = ctx.request_id
            failed_context["execution_id"] = ctx.execution_id
            failed_context["worker_job_id"] = ctx.worker_job_id

    async def invoke() -> None:
        with pytest.raises(ToolError, match="tool failed after context update"):
            await server_instance.call_tool("context_writer_failing", {})

    monkeypatch.setattr(
        "freecad_mcp.instrumented_server.emit_event",
        capture_emit,
    )
    monkeypatch.setattr(server_instance, "get_context", lambda: _context())
    asyncio.run(invoke())

    assert failed_context == {
        "request_id": "worker-request-id",
        "execution_id": "worker-execution-id",
        "worker_job_id": "worker-job-id",
    }


def test_async_tools_remain_on_event_loop(monkeypatch):
    server_instance = InstrumentedFastMCP("worker-async-test")
    loop_ids: list[int] = []

    @server_instance.tool(name="async_probe")
    async def async_probe() -> dict[str, int]:
        loop_ids.append(id(asyncio.get_running_loop()))
        await asyncio.sleep(0)
        return {"loop_id": loop_ids[-1]}

    async def invoke() -> None:
        caller_loop = asyncio.get_running_loop()
        await server_instance.call_tool("async_probe", {})
        assert loop_ids == [id(caller_loop)]

    _silence_telemetry(monkeypatch)
    monkeypatch.setattr(server_instance, "get_context", lambda: _context())
    asyncio.run(invoke())


def test_control_lane_tools_allowlist_matches_registered_mcp_control_tools():
    registered = _registered_mcp_tool_names()

    assert "acknowledge_acquisition_claim" not in registered
    assert "acknowledge_acquisition_claim" not in CONTROL_LANE_TOOLS

    assert "claim_acquisition_result" in registered
    assert "claim_acquisition_result" not in CONTROL_LANE_TOOLS

    assert CONTROL_LANE_TOOLS == frozenset(
        {
            "cancel_request",
            "get_request_status",
        }
    )
    assert CONTROL_LANE_TOOLS <= registered

    assert "execute_code" in registered
    assert "execute_code" not in CONTROL_LANE_TOOLS
    assert "acquire_document_lock" in registered
    assert "acquire_document_lock" not in CONTROL_LANE_TOOLS


def test_string_transport_run_uses_fastmcp_base_without_super_cell(monkeypatch):
    """stdio reconnect must not crash on ``super()`` from a late-bound method.

    ``InstrumentedFastMCP.run`` is a free function assigned onto the class, so
    ``super()`` has no ``__class__`` cell and raises RuntimeError at startup.
    """

    from mcp.server.fastmcp import FastMCP

    server_instance = InstrumentedFastMCP("stdio-run-regression")
    captured: dict[str, object] = {}

    def fake_run(self, transport="stdio", mount_path=None):
        captured["self"] = self
        captured["transport"] = transport
        captured["mount_path"] = mount_path
        return "started"

    monkeypatch.setattr(FastMCP, "run", fake_run)

    result = server_instance.run(transport="stdio", mount_path=None)

    assert result == "started"
    assert captured["self"] is server_instance
    assert captured["transport"] == "stdio"
    assert captured["mount_path"] is None
