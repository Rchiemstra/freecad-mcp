"""P7 regression tests: worker-thread boundary for control, idempotency, handoff."""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.instrumented_server import InstrumentedFastMCP
from freecad_mcp.lease_manager import LeaseClientManager, LeaseCredential
from freecad_mcp.outcomes import OutcomeStatus
from freecad_mcp.operations.locking import (
    adopt_dirty_document_operation,
    claim_acquisition_result_operation,
)


pytestmark = pytest.mark.unit


def _context() -> SimpleNamespace:
    return SimpleNamespace(
        request_id="protocol-call",
        request_context=SimpleNamespace(meta=None, experimental=None),
    )


def _silence_telemetry(monkeypatch) -> None:
    monkeypatch.setattr(
        "freecad_mcp.instrumented_server.emit_event",
        lambda *_args, **_kwargs: None,
    )


def _request_id(label: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"freecad-mcp-p7:{label}"))


def _credential(session: str, token: str) -> LeaseCredential:
    return LeaseCredential(
        lease_id=f"lease-{session}",
        document_session_uuid=session,
        generation=1,
        token=token,
    )


def _install_worker_server(monkeypatch) -> InstrumentedFastMCP:
    server_instance = InstrumentedFastMCP("p7-worker-boundary")
    _silence_telemetry(monkeypatch)
    monkeypatch.setattr(server_instance, "get_context", lambda: _context())
    return server_instance


@pytest.mark.unit
def test_cancel_request_control_lane_routes_real_rpc_during_long_sync_tool(monkeypatch):
    """D6: cancel_request stays on the control lane and hits invoke_v2 cancel RPC."""
    server_instance = _install_worker_server(monkeypatch)
    connection = FreeCADConnection(timeout=5)
    manager = LeaseClientManager(session_token="rpc-session")
    connection.configure_lease_routing(manager, lambda _name: "")
    general_started = threading.Event()
    general_release = threading.Event()
    cancel_rpc_calls: list[dict[str, Any]] = []

    def invoke_v2(
        method: str,
        params: dict[str, Any],
        _context: Any,
        *,
        control: bool = False,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del _context, timeout, kwargs
        if method != "cancel_request":
            raise AssertionError(f"unexpected invoke_v2 method: {method!r}")
        assert control is True
        cancel_rpc_calls.append(dict(params))
        return {
            "ok": True,
            "result": {
                "success": True,
                "cancellation": {"status": "requested"},
            },
        }

    connection.invoke_v2 = invoke_v2  # type: ignore[method-assign]
    lane_threads: dict[str, str] = {}

    @server_instance.tool(name="long_execute_code")
    def long_execute_code() -> dict[str, str]:
        lane_threads["general"] = threading.current_thread().name
        general_started.set()
        if not general_release.wait(timeout=5.0):
            raise TimeoutError("long_execute_code was not released")
        return {"status": "done"}

    @server_instance.tool(name="cancel_request")
    def cancel_request_tool(request_id: str) -> dict[str, object]:
        lane_threads["control"] = threading.current_thread().name
        return connection.cancel_request(request_id)

    async def run() -> None:
        general_task = asyncio.create_task(
            server_instance.call_tool("long_execute_code", {})
        )
        deadline = asyncio.get_running_loop().time() + 2.0
        while not general_started.is_set():
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("long_execute_code did not start")
            await asyncio.sleep(0.01)

        target_request_id = _request_id("cancel-during-long-sync")
        started = asyncio.get_running_loop().time()
        result = await asyncio.wait_for(
            server_instance.call_tool(
                "cancel_request",
                {"request_id": target_request_id},
            ),
            timeout=1.0,
        )
        elapsed = asyncio.get_running_loop().time() - started

        assert result["success"] is True
        assert result["cancellation"]["status"] == "requested"
        assert cancel_rpc_calls == [{"target_request_id": target_request_id}]
        assert lane_threads["control"].startswith("mcp-control-tool")
        assert lane_threads["general"].startswith("mcp-sync-tool")
        assert lane_threads["control"] != lane_threads["general"]
        assert elapsed < 0.5

        general_release.set()
        await asyncio.wait_for(general_task, timeout=5.0)

    asyncio.run(run())
    connection.disconnect()


@pytest.mark.unit
def test_idempotent_acquire_reuses_local_credential_on_redacted_replay(
    monkeypatch, tmp_path
):
    server_instance = _install_worker_server(monkeypatch)
    connection = FreeCADConnection(timeout=5)
    model = tmp_path / "Replayed.FCStd"
    credential = _credential("doc-replayed", "one-time-replayed-token")
    manager = LeaseClientManager(session_token="rpc-session")
    manager.store(credential, canonical_paths=(model,))
    connection.configure_lease_routing(manager, lambda _name: "doc-replayed")
    adopt_calls = 0
    request_id = _request_id("adopt-replay")

    def adopt_dirty_document(**_kwargs):
        nonlocal adopt_calls
        adopt_calls += 1
        wire = credential.to_wire()
        if adopt_calls == 1:
            return {
                "success": True,
                "request_id": request_id,
                "document": {
                    "name": "Replayed",
                    "canonical_path": str(model),
                },
                "credential": wire,
                "lease": {"state": "LOCKED_IDLE"},
            }
        redacted_wire = dict(wire)
        redacted_wire["token"] = "[REDACTED]"
        return {
            "success": True,
            "request_id": request_id,
            "document": {
                "name": "Replayed",
                "canonical_path": str(model),
            },
            "credential": redacted_wire,
            "lease": {"state": "LOCKED_IDLE"},
        }

    monkeypatch.setattr(connection, "adopt_dirty_document", adopt_dirty_document)
    monkeypatch.setattr(connection, "acknowledge_acquisition_claim", mock.Mock())
    document_sessions: dict[str, str] = {}
    observed_threads: list[str] = []
    structured_results: list[dict[str, Any]] = []

    @server_instance.tool(name="acquire_document_lock")
    def acquire_document_lock(doc_name: str) -> dict[str, object]:
        observed_threads.append(threading.current_thread().name)
        response = adopt_dirty_document_operation(
            connection,
            selector={"document_name": doc_name},
            lease_manager=manager,
            document_sessions=document_sessions,
        )
        structured = response.structuredContent or {}
        structured_results.append(structured)
        text = "".join(
            getattr(block, "text", "") or str(block) for block in response.content
        )
        return {
            "is_error": response.isError,
            "text": text,
            "structured": structured,
        }

    async def run() -> None:
        first = await server_instance.call_tool(
            "acquire_document_lock",
            {"doc_name": "Replayed"},
        )
        second = await server_instance.call_tool(
            "acquire_document_lock",
            {"doc_name": "Replayed"},
        )

        assert first["is_error"] is False
        assert second["is_error"] is False
        assert adopt_calls == 2
        assert structured_results[0]["credential_stored"] is True
        assert structured_results[1]["credential_stored"] is True
        assert manager.require(document_session_uuid="doc-replayed") == credential
        assert document_sessions == {"Replayed": "doc-replayed"}
        assert all(name.startswith("mcp-sync-tool") for name in observed_threads)
        connection.acknowledge_acquisition_claim.assert_called_once_with(request_id)
        rendered = json.dumps({"first": first, "second": second}, default=str)
        assert "one-time-replayed-token" not in rendered

    asyncio.run(run())
    connection.disconnect()


@pytest.mark.unit
def test_handoff_poll_and_claim_through_worker_threads(monkeypatch):
    server_instance = _install_worker_server(monkeypatch)
    request_id = _request_id("handoff-worker")
    claim_token = "secret-handoff-claim-token"
    freecad = mock.Mock()
    freecad.get_request_status.return_value = {
        "success": True,
        "state": "completed",
        "result_claimable": True,
    }
    freecad.claim_acquisition_result.return_value = {
        "success": True,
        "request_id": request_id,
        "credential": {
            "lease_id": "lease-handoff",
            "document_session_uuid": "doc-handoff",
            "generation": 2,
            "token": claim_token,
        },
        "document": {"name": "HandoffDoc", "canonical_path": "C:/tmp/Handoff.FCStd"},
        "lease": {"state": "LOCKED_IDLE"},
    }
    manager = LeaseClientManager(session_token="rpc-session")
    document_sessions: dict[str, str] = {}
    lane_threads: dict[str, str] = {}

    @server_instance.tool(name="get_request_status")
    def get_request_status(request_id: str) -> dict[str, object]:
        lane_threads["status"] = threading.current_thread().name
        result = freecad.get_request_status(request_id)
        return result

    @server_instance.tool(name="claim_acquisition_result")
    def claim_acquisition_result(request_id: str) -> dict[str, object]:
        lane_threads["claim"] = threading.current_thread().name
        response = claim_acquisition_result_operation(
            freecad,
            request_id=request_id,
            lease_manager=manager,
            document_sessions=document_sessions,
        )
        structured = response.structuredContent or {}
        text = "".join(
            getattr(block, "text", "") or str(block) for block in response.content
        )
        return {
            "is_error": response.isError,
            "text": text,
            "structured": structured,
        }

    async def run() -> None:
        status = await server_instance.call_tool(
            "get_request_status",
            {"request_id": request_id},
        )
        claim = await server_instance.call_tool(
            "claim_acquisition_result",
            {"request_id": request_id},
        )

        assert status["state"] == "completed"
        assert status["result_claimable"] is True
        assert claim["is_error"] is False
        assert manager.require(document_session_uuid="doc-handoff").token == claim_token
        assert document_sessions == {"HandoffDoc": "doc-handoff"}
        assert lane_threads["status"].startswith("mcp-control-tool")
        assert lane_threads["claim"].startswith("mcp-sync-tool")
        rendered = json.dumps(claim, default=str)
        assert claim_token not in rendered
        freecad.acknowledge_acquisition_claim.assert_called_once_with(request_id)

    asyncio.run(run())


@pytest.mark.unit
def test_credential_redaction_preserved_across_worker_thread_marshalling(monkeypatch):
    server_instance = _install_worker_server(monkeypatch)
    request_id = _request_id("redaction-worker")
    token = "must-not-leak-through-worker"
    freecad = mock.Mock()
    freecad.claim_acquisition_result.return_value = {
        "success": True,
        "request_id": request_id,
        "credential": {
            "lease_id": "lease-redacted",
            "document_session_uuid": "doc-redacted",
            "generation": 1,
            "token": token,
        },
        "document": {"name": "Redacted", "canonical_path": "C:/tmp/Redacted.FCStd"},
        "lease": {"state": "LOCKED_IDLE"},
    }
    manager = LeaseClientManager(session_token="rpc-session")
    document_sessions: dict[str, str] = {}

    @server_instance.tool(name="claim_acquisition_result")
    def claim_acquisition_result(request_id: str) -> dict[str, object]:
        response = claim_acquisition_result_operation(
            freecad,
            request_id=request_id,
            lease_manager=manager,
            document_sessions=document_sessions,
        )
        structured = response.structuredContent or {}
        text = "".join(
            getattr(block, "text", "") or str(block) for block in response.content
        )
        return {
            "is_error": response.isError,
            "text": text,
            "structured": structured,
            "repr": repr(response),
        }

    async def run() -> None:
        result = await server_instance.call_tool(
            "claim_acquisition_result",
            {"request_id": request_id},
        )

        assert result["is_error"] is False
        assert manager.require(document_session_uuid="doc-redacted").token == token
        rendered = json.dumps(result, default=str)
        assert token not in rendered
        assert token not in result["repr"]

    asyncio.run(run())


@pytest.mark.unit
def test_handoff_pending_adopt_routes_through_worker_without_token_export(monkeypatch):
    server_instance = _install_worker_server(monkeypatch)
    request_id = _request_id("handoff-pending-worker")
    freecad = mock.Mock()
    freecad.adopt_dirty_document.return_value = {
        "success": False,
        "error_code": "LOCKED_ERROR_HANDOFF_PENDING",
        "error": "Automatic LOCKED_ERROR handoff is processing",
        "request_id": request_id,
        "confirmation_pending": False,
        "handoff_pending": True,
    }
    manager = LeaseClientManager(session_token="rpc-session")
    document_sessions: dict[str, str] = {}

    @server_instance.tool(name="adopt_dirty_document")
    def adopt_dirty_document(document_name: str) -> dict[str, object]:
        assert threading.current_thread().name.startswith("mcp-sync-tool")
        response = adopt_dirty_document_operation(
            freecad,
            selector={"document_name": document_name},
            lease_manager=manager,
            document_sessions=document_sessions,
        )
        text = "".join(
            getattr(block, "text", "") or str(block) for block in response.content
        )
        return {
            "is_error": response.isError,
            "text": text,
            "structured": response.structuredContent or {},
        }

    async def run() -> None:
        result = await server_instance.call_tool(
            "adopt_dirty_document",
            {"document_name": "Dirty"},
        )

        assert result["is_error"] is False
        assert request_id in result["text"]
        assert "get_request_status" in result["text"]
        assert "claim_acquisition_result" in result["text"]
        assert freecad.get_request_status.call_count == 0

    asyncio.run(run())


@pytest.mark.unit
def test_cancelled_sync_tool_does_not_emit_false_succeeded_telemetry(
    monkeypatch,
):
    """CancelledError is BaseException; sync worker cancel must not report success."""
    server_instance = _install_worker_server(monkeypatch)
    started = threading.Event()
    release = threading.Event()
    completion_events: list[dict[str, Any]] = []

    @server_instance.tool(name="blocking_sync_probe")
    def blocking_sync_probe() -> dict[str, str]:
        started.set()
        if not release.wait(timeout=5.0):
            raise TimeoutError("blocking_sync_probe was not released")
        return {"status": "done"}

    def capture_emit(stage, event, **kwargs) -> None:
        if stage == "mcp" and event == "tool_call_completed":
            payload = kwargs.get("payload") or {}
            completion_events.append(
                {
                    "status": kwargs.get("status"),
                    "tool": payload.get("tool"),
                }
            )

    monkeypatch.setattr(
        "freecad_mcp.instrumented_server.emit_event",
        capture_emit,
    )

    async def run() -> None:
        tool_task = asyncio.create_task(
            server_instance.call_tool("blocking_sync_probe", {})
        )
        deadline = asyncio.get_running_loop().time() + 2.0
        while not started.is_set():
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("blocking_sync_probe did not start")
            await asyncio.sleep(0.01)

        tool_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tool_task

        release.set()

    asyncio.run(run())

    blocking_events = [
        event
        for event in completion_events
        if event.get("tool") == "blocking_sync_probe"
    ]
    assert blocking_events
    assert all(
        event["status"] != OutcomeStatus.SUCCEEDED.value
        for event in blocking_events
    )
    assert any(
        event["status"] == OutcomeStatus.CANCELLED.value
        for event in blocking_events
    )


@pytest.mark.unit
def test_worker_context_updates_survive_control_lane_cancellation(monkeypatch):
    server_instance = _install_worker_server(monkeypatch)
    completed_context: dict[str, str] = {}

    @server_instance.tool(name="cancel_request")
    def cancel_request(request_id: str) -> dict[str, str]:
        from freecad_mcp.telemetry.context import update_context

        update_context(
            request_id="worker-cancel-request-id",
            execution_id="worker-cancel-execution-id",
            worker_job_id="worker-cancel-job-id",
        )
        return {"status": "cancelled", "request_id": request_id}

    def capture_emit(stage, event, **_kwargs) -> None:
        if stage == "mcp" and event == "tool_call_completed":
            from freecad_mcp.telemetry.context import get_context

            ctx = get_context()
            completed_context["request_id"] = ctx.request_id
            completed_context["execution_id"] = ctx.execution_id
            completed_context["worker_job_id"] = ctx.worker_job_id

    monkeypatch.setattr(
        "freecad_mcp.instrumented_server.emit_event",
        capture_emit,
    )

    async def run() -> None:
        await server_instance.call_tool(
            "cancel_request",
            {"request_id": _request_id("context-cancel")},
        )

    asyncio.run(run())

    assert completed_context == {
        "request_id": "worker-cancel-request-id",
        "execution_id": "worker-cancel-execution-id",
        "worker_job_id": "worker-cancel-job-id",
    }


@pytest.mark.unit
def test_sync_worker_failure_still_merges_context_on_control_lane(monkeypatch):
    server_instance = _install_worker_server(monkeypatch)
    failed_context: dict[str, str] = {}

    @server_instance.tool(name="get_request_status")
    def get_request_status(request_id: str) -> dict[str, str]:
        from freecad_mcp.telemetry.context import update_context

        update_context(
            request_id="worker-status-request-id",
            execution_id="worker-status-execution-id",
            worker_job_id="worker-status-job-id",
        )
        raise ToolError(f"status failed for {request_id}")

    def capture_emit(stage, event, **_kwargs) -> None:
        if stage == "mcp" and event == "tool_call_completed":
            from freecad_mcp.telemetry.context import get_context

            ctx = get_context()
            failed_context["request_id"] = ctx.request_id
            failed_context["execution_id"] = ctx.execution_id
            failed_context["worker_job_id"] = ctx.worker_job_id

    monkeypatch.setattr(
        "freecad_mcp.instrumented_server.emit_event",
        capture_emit,
    )

    async def run() -> None:
        with pytest.raises(ToolError, match="status failed"):
            await server_instance.call_tool(
                "get_request_status",
                {"request_id": _request_id("context-failure")},
            )

    asyncio.run(run())

    assert failed_context == {
        "request_id": "worker-status-request-id",
        "execution_id": "worker-status-execution-id",
        "worker_job_id": "worker-status-job-id",
    }
