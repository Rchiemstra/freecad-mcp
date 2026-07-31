"""Automatic stale-lease recovery orchestration (P5 / D7-D8)."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any
from types import SimpleNamespace
from unittest import mock
import uuid

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.lease_manager import (
    REVOCATION_ERROR_CODES,
    STALE_RECOVERY_OUTCOME_RECOVERED,
    STALE_RECOVERY_OUTCOME_REFUSED_RETRYABLE,
    STALE_RECOVERY_OUTCOME_REFUSED_TERMINAL,
    STALE_RECOVERY_OUTCOME_SKIPPED_BACKOFF,
    STALE_RECOVERY_OUTCOME_SKIPPED_TERMINAL,
    STALE_RECOVERY_RETRY_ERROR_CODE,
    STALE_RECOVERY_TRIGGER_HEARTBEAT,
    STALE_RECOVERY_TRIGGER_POST_TOOL,
    LeaseClientManager,
    LeaseCredential,
    RpcRequestContext,
    StaleLeaseRecoveryOrchestrator,
    extract_stale_sessions_from_heartbeat,
    is_timeout_stale_heartbeat_item,
    reconcile_refusal_is_terminal,
)
from freecad_mcp import server
from freecad_mcp.instrumented_server import InstrumentedFastMCP


def _mcp_context():
    return SimpleNamespace(
        request_id="protocol-call",
        request_context=SimpleNamespace(meta=None, experimental=None),
    )


def _credential(session: str, token: str) -> LeaseCredential:
    return LeaseCredential(
        lease_id=f"lease-{session}",
        document_session_uuid=session,
        generation=1,
        token=token,
    )


def _request_context(session: str, token: str) -> RpcRequestContext:
    return RpcRequestContext(
        request_id=str(uuid.uuid4()),
        session_token="rpc-session",
        lease_credentials=(_credential(session, token),),
        operation_name="Protected edit",
    )


@pytest.mark.unit
def test_stale_is_not_a_revocation_error_code():
    assert "STALE" not in REVOCATION_ERROR_CODES
    assert "LEASE_STALE" not in REVOCATION_ERROR_CODES


@pytest.mark.unit
def test_stale_heartbeat_item_retains_credential(tmp_path):
    manager = LeaseClientManager(session_token="rpc-session")
    path = tmp_path / "model.FCStd"
    manager.store(_credential("doc-a", "secret-a"), canonical_paths=[path])

    revoked = manager.apply_heartbeat_response(
        {
            "leases": [
                {
                    "document_session_uuid": "doc-a",
                    "success": False,
                    "error_code": "LEASE_STATE_FORBIDS_OPERATION",
                    "revoked": True,
                    "details": {"state": "STALE"},
                }
            ]
        }
    )

    assert revoked == ()
    assert manager.get(document_session_uuid="doc-a") is not None
    rendered = json.dumps(manager.redacted_status(), sort_keys=True)
    assert "secret-a" not in rendered


@pytest.mark.unit
def test_extract_stale_sessions_from_heartbeat_batch():
    response = {
        "leases": [
            {
                "document_session_uuid": "doc-a",
                "error_code": "LEASE_STATE_FORBIDS_OPERATION",
                "details": {"state": "STALE"},
            },
            {
                "document_session_uuid": "doc-b",
                "state": "LOCKED_IDLE",
                "success": True,
            },
        ]
    }
    assert extract_stale_sessions_from_heartbeat(response) == ("doc-a",)
    assert is_timeout_stale_heartbeat_item(response["leases"][0]) is True
    assert is_timeout_stale_heartbeat_item(response["leases"][1]) is False


@pytest.mark.unit
def test_heartbeat_trigger_invokes_reconcile():
    orchestrator = StaleLeaseRecoveryOrchestrator()
    calls: list[tuple[str, str]] = []

    def reconcile(session_uuid: str) -> dict[str, Any]:
        calls.append((session_uuid, STALE_RECOVERY_TRIGGER_HEARTBEAT))
        return {"success": True}

    stale = orchestrator.observe_heartbeat_batch(
        {
            "leases": [
                {
                    "document_session_uuid": "doc-a",
                    "error_code": "LEASE_STATE_FORBIDS_OPERATION",
                    "details": {"state": "STALE"},
                }
            ]
        }
    )

    async def run() -> None:
        results = await orchestrator.recover_sessions(
            stale, STALE_RECOVERY_TRIGGER_HEARTBEAT, reconcile
        )
        assert calls == [("doc-a", STALE_RECOVERY_TRIGGER_HEARTBEAT)]
        assert results["doc-a"].outcome == STALE_RECOVERY_OUTCOME_RECOVERED
        assert orchestrator.sessions_needing_recovery(("doc-a",)) == ()

    asyncio.run(run())


@pytest.mark.unit
def test_post_tool_trigger_marks_held_leases_for_recovery():
    orchestrator = StaleLeaseRecoveryOrchestrator(stale_after_seconds=1.0)
    calls: list[str] = []

    affected = orchestrator.observe_tool_completion(
        2.0, ("doc-a", "doc-b")
    )
    assert affected == ("doc-a", "doc-b")

    async def run() -> None:
        results = await orchestrator.recover_sessions(
            affected,
            STALE_RECOVERY_TRIGGER_POST_TOOL,
            lambda session_uuid: calls.append(session_uuid) or {"success": True},
        )
        assert set(calls) == {"doc-a", "doc-b"}
        assert all(
            item.outcome == STALE_RECOVERY_OUTCOME_RECOVERED
            for item in results.values()
        )

    asyncio.run(run())


@pytest.mark.unit
def test_pre_operation_lazy_recovery_before_protected_rpc():
    orchestrator = StaleLeaseRecoveryOrchestrator()
    orchestrator.mark_needs_recovery("doc-a")
    loop = asyncio.new_event_loop()
    orchestrator.bind_event_loop(loop)
    connection = FreeCADConnection(host="127.0.0.1", port=1)
    connection.configure_lease_routing(
        LeaseClientManager(session_token="rpc-session"),
        lambda _name: "doc-a",
    )
    connection.configure_stale_recovery(orchestrator)

    reconcile_calls: list[str] = []

    def fake_reconcile(session_uuid: str) -> dict[str, Any]:
        reconcile_calls.append(session_uuid)
        return {"success": True}

    with mock.patch.object(
        connection, "reconcile_document_lease", side_effect=fake_reconcile
    ), mock.patch.object(
        connection,
        "invoke_rpc",
        return_value={"ok": True, "result": {"success": True}},
    ):
        context = _request_context("doc-a", "secret-a")
        connection.invoke_v2("edit_object", {"document": "Doc"}, context)

    assert reconcile_calls == ["doc-a"]
    loop.close()


@pytest.mark.unit
def test_per_document_lock_serializes_concurrent_recovery():
    orchestrator = StaleLeaseRecoveryOrchestrator()
    orchestrator.mark_needs_recovery("doc-a")
    active = 0
    peak = 0
    lock = threading.Lock()

    def slow_reconcile(_session_uuid: str) -> dict[str, Any]:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return {"success": True}

    async def run() -> None:
        await asyncio.gather(
            orchestrator.recover_sessions(
                ("doc-a",), STALE_RECOVERY_TRIGGER_HEARTBEAT, slow_reconcile
            ),
            orchestrator.recover_sessions(
                ("doc-a",), STALE_RECOVERY_TRIGGER_POST_TOOL, slow_reconcile
            ),
        )

    asyncio.run(run())
    assert peak == 1


@pytest.mark.unit
def test_refused_reconcile_backoffs_instead_of_tight_loop():
    orchestrator = StaleLeaseRecoveryOrchestrator()
    orchestrator.mark_needs_recovery("doc-a")
    attempts = 0

    def refuse(_session_uuid: str) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        return {
            "success": False,
            "error_code": "BASELINE_MISMATCH",
        }

    async def run() -> None:
        first = await orchestrator.recover_sessions(
            ("doc-a",), STALE_RECOVERY_TRIGGER_HEARTBEAT, refuse
        )
        second = await orchestrator.recover_sessions(
            ("doc-a",), STALE_RECOVERY_TRIGGER_HEARTBEAT, refuse
        )
        assert attempts == 1
        assert first["doc-a"].outcome == STALE_RECOVERY_OUTCOME_REFUSED_RETRYABLE
        assert second["doc-a"].outcome == STALE_RECOVERY_OUTCOME_SKIPPED_BACKOFF

    asyncio.run(run())


@pytest.mark.unit
def test_terminal_refusal_stops_future_attempts():
    orchestrator = StaleLeaseRecoveryOrchestrator()
    orchestrator.mark_needs_recovery("doc-a")
    attempts = 0

    def terminal_refuse(_session_uuid: str) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        return {
            "success": False,
            "error_code": "LEASE_STATE_FORBIDS_OPERATION",
            "details": {"state": "USER_INTERVENED"},
        }

    async def run() -> None:
        first = await orchestrator.recover_sessions(
            ("doc-a",), STALE_RECOVERY_TRIGGER_HEARTBEAT, terminal_refuse
        )
        orchestrator.mark_needs_recovery("doc-a")
        second = await orchestrator.recover_sessions(
            ("doc-a",), STALE_RECOVERY_TRIGGER_HEARTBEAT, terminal_refuse
        )
        assert attempts == 1
        assert first["doc-a"].outcome == STALE_RECOVERY_OUTCOME_REFUSED_TERMINAL
        assert second["doc-a"].outcome == STALE_RECOVERY_OUTCOME_SKIPPED_TERMINAL

    asyncio.run(run())


@pytest.mark.unit
def test_live_document_validation_failed_is_terminal():
    response = {
        "success": False,
        "error_code": "LIVE_DOCUMENT_VALIDATION_FAILED",
    }
    assert reconcile_refusal_is_terminal(response) is True

    orchestrator = StaleLeaseRecoveryOrchestrator()
    orchestrator.mark_needs_recovery("doc-a")
    attempts = 0

    def refuse(_session_uuid: str) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        return response

    async def run() -> None:
        first = await orchestrator.recover_sessions(
            ("doc-a",), STALE_RECOVERY_TRIGGER_HEARTBEAT, refuse
        )
        orchestrator.mark_needs_recovery("doc-a")
        second = await orchestrator.recover_sessions(
            ("doc-a",), STALE_RECOVERY_TRIGGER_HEARTBEAT, refuse
        )
        assert attempts == 1
        assert first["doc-a"].outcome == STALE_RECOVERY_OUTCOME_REFUSED_TERMINAL
        assert second["doc-a"].outcome == STALE_RECOVERY_OUTCOME_SKIPPED_TERMINAL

    asyncio.run(run())


@pytest.mark.unit
def test_lease_coordination_lost_is_terminal():
    response = {
        "success": False,
        "error_code": "LEASE_COORDINATION_LOST",
    }
    assert reconcile_refusal_is_terminal(response) is True

    orchestrator = StaleLeaseRecoveryOrchestrator()
    orchestrator.mark_needs_recovery("doc-a")
    attempts = 0

    def refuse(_session_uuid: str) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        return response

    async def run() -> None:
        first = await orchestrator.recover_sessions(
            ("doc-a",), STALE_RECOVERY_TRIGGER_HEARTBEAT, refuse
        )
        orchestrator.mark_needs_recovery("doc-a")
        second = await orchestrator.recover_sessions(
            ("doc-a",), STALE_RECOVERY_TRIGGER_HEARTBEAT, refuse
        )
        assert attempts == 1
        assert first["doc-a"].outcome == STALE_RECOVERY_OUTCOME_REFUSED_TERMINAL
        assert second["doc-a"].outcome == STALE_RECOVERY_OUTCOME_SKIPPED_TERMINAL

    asyncio.run(run())


@pytest.mark.unit
def test_rpc_stale_refusal_returns_retryable_without_replay():
    orchestrator = StaleLeaseRecoveryOrchestrator()
    loop = asyncio.new_event_loop()
    orchestrator.bind_event_loop(loop)
    connection = FreeCADConnection(host="127.0.0.1", port=1)
    connection.configure_lease_routing(
        LeaseClientManager(session_token="rpc-session"),
        lambda _name: "doc-a",
    )
    connection.configure_stale_recovery(orchestrator)

    rpc_calls = 0

    def fake_invoke_rpc(*_args, **_kwargs):
        nonlocal rpc_calls
        rpc_calls += 1
        return {
            "ok": False,
            "error": {
                "code": "LEASE_STATE_FORBIDS_OPERATION",
                "message": "state STALE forbids this operation",
            },
            "error_code": "LEASE_STATE_FORBIDS_OPERATION",
            "details": {"state": "STALE"},
        }

    with mock.patch.object(connection, "invoke_rpc", side_effect=fake_invoke_rpc), mock.patch.object(
        connection,
        "reconcile_document_lease",
        return_value={"success": True},
    ):
        context = _request_context("doc-a", "secret-a")
        response = connection.invoke_v2(
            "edit_object", {"document": "Doc"}, context
        )

    assert rpc_calls == 1
    assert response["error_code"] == STALE_RECOVERY_RETRY_ERROR_CODE
    assert response["retryable"] is True
    assert response["mutation_replayed"] is False
    assert response["stale_recovery_succeeded"] is True
    loop.close()


@pytest.mark.unit
def test_rpc_stale_refusal_with_mutation_flag_still_recovers():
    orchestrator = StaleLeaseRecoveryOrchestrator()
    loop = asyncio.new_event_loop()
    orchestrator.bind_event_loop(loop)
    connection = FreeCADConnection(host="127.0.0.1", port=1)
    connection.configure_lease_routing(
        LeaseClientManager(session_token="rpc-session"),
        lambda _name: "doc-a",
    )
    connection.configure_stale_recovery(orchestrator)

    reconcile_calls = 0

    def fake_invoke_rpc(*_args, **_kwargs):
        return {
            "ok": False,
            "error": {
                "code": "LEASE_STATE_FORBIDS_OPERATION",
                "message": "state STALE forbids this operation",
            },
            "error_code": "LEASE_STATE_FORBIDS_OPERATION",
            "details": {"state": "STALE", "mutation_may_have_begun": True},
            "mutation_may_have_begun": True,
        }

    def fake_reconcile(session_uuid: str) -> dict[str, Any]:
        nonlocal reconcile_calls
        reconcile_calls += 1
        assert session_uuid == "doc-a"
        return {"success": True}

    with mock.patch.object(
        connection, "invoke_rpc", side_effect=fake_invoke_rpc
    ), mock.patch.object(
        connection, "reconcile_document_lease", side_effect=fake_reconcile
    ):
        context = _request_context("doc-a", "secret-a")
        response = connection.invoke_v2("edit_object", {"document": "Doc"}, context)

    assert reconcile_calls == 1
    assert response["error_code"] == STALE_RECOVERY_RETRY_ERROR_CODE
    assert response["retryable"] is True
    assert response["mutation_replayed"] is False
    assert response["stale_recovery_succeeded"] is True
    loop.close()


@pytest.mark.unit
def test_post_tool_reconcile_exception_does_not_fail_successful_tool():
    orchestrator = StaleLeaseRecoveryOrchestrator(stale_after_seconds=0.01)
    manager = LeaseClientManager(session_token="rpc-session")
    manager.store(_credential("doc-a", "secret-a"))
    connection = mock.Mock()
    connection.reconcile_document_lease.side_effect = RuntimeError("reconcile blew up")

    async def run() -> None:
        with mock.patch.object(server, "state") as state_mock, mock.patch.object(
            server, "stale_recovery", orchestrator
        ):
            state_mock.lease_manager = manager
            state_mock.freecad_connection = connection
            await server._post_tool_stale_recovery(0.5, "execute_code")

    asyncio.run(run())
    connection.reconcile_document_lease.assert_called_once_with("doc-a")


@pytest.mark.unit
def test_instrumented_server_runs_post_tool_hook_on_tool_exception():
    server_instance = InstrumentedFastMCP("post-tool-exception-test")
    hook_calls: list[tuple[float, str]] = []

    async def failing_hook(duration_s: float, tool_name: str) -> None:
        hook_calls.append((duration_s, tool_name))

    server_instance.post_tool_completed_hook = failing_hook

    @server_instance.tool(name="boom_probe")
    def boom_probe() -> str:
        raise ValueError("tool failed")

    async def run() -> None:
        with mock.patch(
            "freecad_mcp.instrumented_server.emit_event",
            lambda *_args, **_kwargs: None,
        ), mock.patch.object(
            server_instance, "get_context", lambda: _mcp_context()
        ):
            with pytest.raises(ToolError, match="tool failed"):
                await server_instance.call_tool("boom_probe", {})

    asyncio.run(run())
    assert len(hook_calls) == 1
    assert hook_calls[0][1] == "boom_probe"
    assert hook_calls[0][0] >= 0.0


@pytest.mark.unit
def test_instrumented_server_post_tool_hook_failure_preserves_tool_success():
    server_instance = InstrumentedFastMCP("post-tool-hook-failure-test")

    async def exploding_hook(_duration_s: float, _tool_name: str) -> None:
        raise RuntimeError("hook failed")

    server_instance.post_tool_completed_hook = exploding_hook

    @server_instance.tool(name="ok_probe")
    def ok_probe() -> dict[str, str]:
        return {"status": "ok"}

    async def run() -> None:
        with mock.patch(
            "freecad_mcp.instrumented_server.emit_event",
            lambda *_args, **_kwargs: None,
        ), mock.patch.object(
            server_instance, "get_context", lambda: _mcp_context()
        ):
            result = await server_instance.call_tool("ok_probe", {})
        assert result == {"status": "ok"}

    asyncio.run(run())


@pytest.mark.unit
def test_server_heartbeat_once_triggers_reconcile():
    manager = LeaseClientManager(session_token="rpc-session")
    manager.store(_credential("doc-a", "secret-a"))
    connection = mock.Mock()
    connection.heartbeat_document_locks_batch.return_value = {
        "ok": True,
        "result": {
            "success": True,
            "leases": [
                {
                    "document_session_uuid": "doc-a",
                    "error_code": "LEASE_STATE_FORBIDS_OPERATION",
                    "details": {"state": "STALE"},
                }
            ],
        },
    }
    connection.reconcile_document_lease.return_value = {"success": True}

    orchestrator = StaleLeaseRecoveryOrchestrator()

    async def run() -> None:
        with mock.patch.object(server, "state") as state_mock, mock.patch.object(
            server, "stale_recovery", orchestrator
        ), mock.patch.object(server, "_authenticate_connection"), mock.patch.object(
            server, "_connection_lock"
        ):
            state_mock.lease_manager = manager
            state_mock.freecad_connection = connection
            successful = await server._lease_heartbeat_once()
        assert successful is True
        connection.reconcile_document_lease.assert_called_once_with("doc-a")

    asyncio.run(run())


@pytest.mark.unit
def test_post_tool_hook_schedules_recovery_for_long_calls():
    orchestrator = StaleLeaseRecoveryOrchestrator(stale_after_seconds=0.01)
    manager = LeaseClientManager(session_token="rpc-session")
    manager.store(_credential("doc-a", "secret-a"))
    connection = mock.Mock()
    connection.reconcile_document_lease.return_value = {"success": True}

    async def run() -> None:
        with mock.patch.object(server, "state") as state_mock, mock.patch.object(
            server, "stale_recovery", orchestrator
        ):
            state_mock.lease_manager = manager
            state_mock.freecad_connection = connection
            await server._post_tool_stale_recovery(0.5, "execute_code")
        connection.reconcile_document_lease.assert_called_once_with("doc-a")

    asyncio.run(run())
