"""P7 boundary tests: orchestration races, dirty/clean reconcile, lock timing."""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from types import SimpleNamespace
from typing import Any, Mapping
from unittest import mock

import pytest

from freecad_mcp import server
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.instrumented_server import InstrumentedFastMCP
from freecad_mcp.lease_manager import (
    STALE_RECOVERY_OUTCOME_RECOVERED,
    STALE_RECOVERY_OUTCOME_REFUSED_RETRYABLE,
    STALE_RECOVERY_OUTCOME_REFUSED_TERMINAL,
    STALE_RECOVERY_OUTCOME_SKIPPED_TERMINAL,
    STALE_RECOVERY_OUTCOME_SKIPPED_UNNECESSARY,
    STALE_RECOVERY_RETRY_ERROR_CODE,
    STALE_RECOVERY_TRIGGER_HEARTBEAT,
    STALE_RECOVERY_TRIGGER_POST_TOOL,
    STALE_RECOVERY_TRIGGER_PRE_OPERATION,
    LeaseClientManager,
    LeaseCredential,
    RpcRequestContext,
    StaleLeaseRecoveryOrchestrator,
)


def _mcp_context() -> SimpleNamespace:
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


def _sample_baseline() -> dict[str, Any]:
    return {
        "mtime_ns": 1_700_000_000_000_000_000,
        "size": 42,
        "sha256": "stable-baseline-sha256",
        "file_identity": {
            "platform": "win32",
            "volume_serial": 0xDEADBEEF,
            "file_index": 12345,
        },
    }


def _lease_reconcile_wire_result(
    *,
    mode: str,
    snapshot_id: str | None = None,
    canonical_path: str | None = None,
) -> dict[str, Any]:
    """Build reconcile payloads that mirror real saved / never-saved / clean shapes."""

    lease_document: dict[str, Any] = {
        "session_uuid": "wire-session",
        "name": "WireDocument",
    }
    document_state: dict[str, Any] = {
        "dirty": mode != "clean",
        "user_intervened": False,
        "validation_complete": mode == "clean",
        "last_mutation_revision": 1 if mode != "clean" else 0,
    }
    if mode == "never_saved":
        lease_document["canonical_path"] = None
        document_state["snapshot_id"] = snapshot_id
        document_state["validation_complete"] = False
    elif mode == "dirty_saved":
        lease_document["canonical_path"] = canonical_path or "C:/models/dirty-saved.FCStd"
        document_state["baseline"] = _sample_baseline()
        document_state["validation_complete"] = False
    else:
        lease_document["canonical_path"] = canonical_path or "C:/models/saved.FCStd"
        document_state["baseline"] = _sample_baseline()
    return {
        "success": True,
        "lease": {
            "lease": {"state": "LOCKED_IDLE", "generation": 1},
            "document": lease_document,
            "document_state": document_state,
        },
    }


def _observed_document_state(call: Mapping[str, Any]) -> dict[str, Any]:
    document_state = call.get("document_state")
    assert isinstance(document_state, dict)
    return document_state


def _observed_lease_document(call: Mapping[str, Any]) -> dict[str, Any]:
    lease_document = call.get("lease_document")
    assert isinstance(lease_document, dict)
    return lease_document


def _assert_clean_wire_observed(call: Mapping[str, Any]) -> None:
    document_state = _observed_document_state(call)
    lease_document = _observed_lease_document(call)
    assert document_state["dirty"] is False
    assert document_state.get("snapshot_id") in (None, "")
    assert "snapshot_id" not in document_state or document_state.get("snapshot_id") is None
    assert lease_document.get("canonical_path") == "C:/models/saved.FCStd"
    assert document_state.get("baseline") is not None


def _assert_dirty_saved_wire_observed(call: Mapping[str, Any]) -> None:
    document_state = _observed_document_state(call)
    lease_document = _observed_lease_document(call)
    assert document_state["dirty"] is True
    assert document_state.get("baseline") is not None
    assert document_state.get("snapshot_id") in (None, "")
    assert "snapshot_id" not in document_state or document_state.get("snapshot_id") is None
    assert lease_document.get("canonical_path") == "C:/models/dirty-saved.FCStd"


def _assert_never_saved_wire_observed(
    call: Mapping[str, Any],
    *,
    snapshot_id: str,
) -> None:
    document_state = _observed_document_state(call)
    lease_document = _observed_lease_document(call)
    assert document_state["dirty"] is True
    assert document_state.get("snapshot_id") == snapshot_id
    assert document_state.get("baseline") in (None, "")
    assert "baseline" not in document_state or document_state.get("baseline") is None
    assert lease_document.get("canonical_path") in (None, "")
    assert document_state.get("validation_complete") is False


def _install_lease_reconcile_invoke_v2_stub(
    connection: FreeCADConnection,
    *,
    session: str,
    token: str,
    dirty: bool,
    never_saved: bool = False,
) -> tuple[list[dict[str, Any]], str | None]:
    """Spy on invoke_v2 lease_reconcile and enforce dirty / never-saved wire shape."""

    reconcile_calls: list[dict[str, Any]] = []
    snapshot_id = str(uuid.uuid4()) if never_saved else None
    real_invoke_v2 = connection.invoke_v2

    def invoke_v2(
        method: str,
        params: dict[str, Any],
        context: Any,
        *,
        control: bool = False,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if method != "lease_reconcile":
            return real_invoke_v2(
                method,
                params,
                context,
                control=control,
                timeout=timeout,
                **kwargs,
            )
        del timeout, kwargs
        assert control is True
        credential = params.get("credential") or {}
        assert credential["document_session_uuid"] == session
        assert credential["token"] == token
        if never_saved:
            assert snapshot_id is not None
            payload = _lease_reconcile_wire_result(
                mode="never_saved",
                snapshot_id=snapshot_id,
            )
        elif dirty:
            payload = _lease_reconcile_wire_result(mode="dirty_saved")
        else:
            payload = _lease_reconcile_wire_result(mode="clean")
        document_state = payload["lease"]["document_state"]
        lease_document = payload["lease"]["document"]
        if never_saved:
            _assert_never_saved_wire_observed(
                {
                    "document_state": document_state,
                    "lease_document": lease_document,
                },
                snapshot_id=snapshot_id,
            )
        elif dirty:
            _assert_dirty_saved_wire_observed(
                {
                    "document_state": document_state,
                    "lease_document": lease_document,
                }
            )
        else:
            _assert_clean_wire_observed(
                {
                    "document_state": document_state,
                    "lease_document": lease_document,
                }
            )
        reconcile_calls.append(
            {
                "method": method,
                "params": dict(params),
                "document_state": dict(document_state),
                "lease_document": dict(lease_document),
            }
        )
        return {"ok": True, "result": payload}

    connection.invoke_v2 = invoke_v2  # type: ignore[method-assign]
    return reconcile_calls, snapshot_id


def _configure_connection(
    orchestrator: StaleLeaseRecoveryOrchestrator,
    *,
    session: str = "doc-a",
    token: str = "secret-a",
    loop: asyncio.AbstractEventLoop | None = None,
) -> FreeCADConnection:
    if loop is not None:
        orchestrator.bind_event_loop(loop)
    connection = FreeCADConnection(host="127.0.0.1", port=1)
    manager = LeaseClientManager(session_token="rpc-session")
    manager.store(_credential(session, token))
    connection.configure_lease_routing(manager, lambda _name: session)
    connection.configure_stale_recovery(orchestrator)
    return connection


def _rpc_ok_response() -> dict[str, Any]:
    return {"ok": True, "result": {"success": True}}


def _invoke_success(response: dict[str, Any]) -> bool:
    if response.get("ok") is True:
        result = response.get("result")
        if isinstance(result, dict):
            return bool(result.get("success"))
        return True
    return bool(response.get("success"))


@pytest.mark.unit
def test_clean_stale_recovery_via_heartbeat_orchestration():
    orchestrator = StaleLeaseRecoveryOrchestrator()
    loop = asyncio.new_event_loop()
    connection = _configure_connection(orchestrator, loop=loop)
    reconcile_calls, _snapshot_id = _install_lease_reconcile_invoke_v2_stub(
        connection,
        session="doc-a",
        token="secret-a",
        dirty=False,
    )

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
            stale,
            STALE_RECOVERY_TRIGGER_HEARTBEAT,
            connection.reconcile_document_lease,
        )
        assert len(reconcile_calls) == 1
        _assert_clean_wire_observed(reconcile_calls[0])
        assert results["doc-a"].outcome == STALE_RECOVERY_OUTCOME_RECOVERED
        assert orchestrator.sessions_needing_recovery(("doc-a",)) == ()

    asyncio.run(run())
    loop.close()


@pytest.mark.unit
def test_dirty_saved_stale_recovery_via_post_tool_orchestration():
    orchestrator = StaleLeaseRecoveryOrchestrator(stale_after_seconds=0.01)
    loop = asyncio.new_event_loop()
    connection = _configure_connection(
        orchestrator, session="doc-dirty-saved", token="dirty-secret", loop=loop
    )
    reconcile_calls, _snapshot_id = _install_lease_reconcile_invoke_v2_stub(
        connection,
        session="doc-dirty-saved",
        token="dirty-secret",
        dirty=True,
    )

    affected = orchestrator.observe_tool_completion(0.5, ("doc-dirty-saved",))

    async def run() -> None:
        results = await orchestrator.recover_sessions(
            affected,
            STALE_RECOVERY_TRIGGER_POST_TOOL,
            connection.reconcile_document_lease,
        )
        assert len(reconcile_calls) == 1
        _assert_dirty_saved_wire_observed(reconcile_calls[0])
        assert results["doc-dirty-saved"].outcome == STALE_RECOVERY_OUTCOME_RECOVERED

    asyncio.run(run())
    loop.close()


@pytest.mark.unit
def test_never_saved_dirty_d5_recovery_via_connection_reconcile():
    orchestrator = StaleLeaseRecoveryOrchestrator()
    loop = asyncio.new_event_loop()
    connection = _configure_connection(
        orchestrator, session="doc-d5", token="d5-secret", loop=loop
    )
    reconcile_calls, snapshot_id = _install_lease_reconcile_invoke_v2_stub(
        connection,
        session="doc-d5",
        token="d5-secret",
        dirty=True,
        never_saved=True,
    )
    orchestrator.mark_needs_recovery("doc-d5")
    reconcile_responses: list[dict[str, Any]] = []
    original_reconcile = connection.reconcile_document_lease

    def tracked_reconcile(session_uuid: str, **kwargs: Any) -> dict[str, Any]:
        response = original_reconcile(session_uuid, **kwargs)
        reconcile_responses.append(response)
        return response

    results = loop.run_until_complete(
        orchestrator.recover_sessions(
            ("doc-d5",),
            STALE_RECOVERY_TRIGGER_HEARTBEAT,
            tracked_reconcile,
        )
    )

    assert len(reconcile_calls) == 1
    assert snapshot_id is not None
    _assert_never_saved_wire_observed(reconcile_calls[0], snapshot_id=snapshot_id)
    assert len(reconcile_responses) == 1
    response_state = reconcile_responses[0]["lease"]["document_state"]
    assert response_state["snapshot_id"] == snapshot_id
    assert response_state.get("baseline") in (None, "")
    assert reconcile_responses[0]["lease"]["document"]["canonical_path"] in (None, "")
    assert results["doc-d5"].outcome == STALE_RECOVERY_OUTCOME_RECOVERED
    loop.close()


@pytest.mark.unit
def test_clean_stale_recovery_refused_baseline_mismatch_is_retryable():
    orchestrator = StaleLeaseRecoveryOrchestrator()
    orchestrator.mark_needs_recovery("doc-a")

    def refuse(_session_uuid: str) -> dict[str, Any]:
        return {"success": False, "error_code": "BASELINE_MISMATCH"}

    async def run() -> None:
        results = await orchestrator.recover_sessions(
            ("doc-a",), STALE_RECOVERY_TRIGGER_HEARTBEAT, refuse
        )
        assert results["doc-a"].outcome == STALE_RECOVERY_OUTCOME_REFUSED_RETRYABLE
        assert results["doc-a"].reason_code == "BASELINE_MISMATCH"

    asyncio.run(run())


@pytest.mark.unit
def test_dirty_stale_recovery_refused_user_intervened_is_terminal():
    orchestrator = StaleLeaseRecoveryOrchestrator()
    orchestrator.mark_needs_recovery("doc-a")
    attempts = 0

    def refuse(_session_uuid: str) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        return {
            "success": False,
            "error_code": "LEASE_STATE_FORBIDS_OPERATION",
            "details": {"state": "USER_INTERVENED"},
        }

    async def run() -> None:
        first = await orchestrator.recover_sessions(
            ("doc-a",), STALE_RECOVERY_TRIGGER_POST_TOOL, refuse
        )
        orchestrator.mark_needs_recovery("doc-a")
        second = await orchestrator.recover_sessions(
            ("doc-a",), STALE_RECOVERY_TRIGGER_POST_TOOL, refuse
        )
        assert attempts == 1
        assert first["doc-a"].outcome == STALE_RECOVERY_OUTCOME_REFUSED_TERMINAL
        assert second["doc-a"].outcome == STALE_RECOVERY_OUTCOME_SKIPPED_TERMINAL

    asyncio.run(run())


@pytest.mark.unit
@pytest.mark.parametrize("dirty", [False, True])
def test_pre_operation_lazy_recovery_before_protected_rpc(dirty: bool):
    orchestrator = StaleLeaseRecoveryOrchestrator()
    loop = asyncio.new_event_loop()
    connection = _configure_connection(orchestrator, loop=loop)
    reconcile_calls, snapshot_id = _install_lease_reconcile_invoke_v2_stub(
        connection,
        session="doc-a",
        token="secret-a",
        dirty=dirty,
    )
    orchestrator.mark_needs_recovery("doc-a")

    with mock.patch.object(
        connection,
        "invoke_rpc",
        return_value=_rpc_ok_response(),
    ):
        context = _request_context("doc-a", "secret-a")
        response = connection.invoke_v2("edit_object", {"document": "Doc"}, context)

    assert len(reconcile_calls) == 1
    if dirty:
        _assert_dirty_saved_wire_observed(reconcile_calls[0])
    else:
        _assert_clean_wire_observed(reconcile_calls[0])
    assert _invoke_success(response) is True
    assert orchestrator.sessions_needing_recovery(("doc-a",)) == ()
    loop.close()


@pytest.mark.unit
@pytest.mark.parametrize("dirty", [False, True])
def test_rpc_stale_refusal_recovers_clean_or_dirty_without_replay(dirty: bool):
    orchestrator = StaleLeaseRecoveryOrchestrator()
    loop = asyncio.new_event_loop()
    connection = _configure_connection(orchestrator, loop=loop)
    reconcile_calls, snapshot_id = _install_lease_reconcile_invoke_v2_stub(
        connection,
        session="doc-a",
        token="secret-a",
        dirty=dirty,
    )
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

    with mock.patch.object(connection, "invoke_rpc", side_effect=fake_invoke_rpc):
        context = _request_context("doc-a", "secret-a")
        response = connection.invoke_v2("edit_object", {"document": "Doc"}, context)

    assert rpc_calls == 1
    assert len(reconcile_calls) == 1
    if dirty:
        _assert_dirty_saved_wire_observed(reconcile_calls[0])
    else:
        _assert_clean_wire_observed(reconcile_calls[0])
    assert response["error_code"] == STALE_RECOVERY_RETRY_ERROR_CODE
    assert response["retryable"] is True
    assert response["mutation_replayed"] is False
    assert response["stale_recovery_succeeded"] is True
    rendered = json.dumps(response, sort_keys=True)
    assert "secret-a" not in rendered
    loop.close()


@pytest.mark.unit
def test_never_saved_dirty_d5_end_to_end_via_client_orchestration():
    orchestrator = StaleLeaseRecoveryOrchestrator()
    loop = asyncio.new_event_loop()
    connection = _configure_connection(
        orchestrator, session="doc-d5", token="d5-secret", loop=loop
    )
    reconcile_calls, snapshot_id = _install_lease_reconcile_invoke_v2_stub(
        connection,
        session="doc-d5",
        token="d5-secret",
        dirty=True,
        never_saved=True,
    )
    orchestrator.observe_heartbeat_batch(
        {
            "leases": [
                {
                    "document_session_uuid": "doc-d5",
                    "error_code": "LEASE_STATE_FORBIDS_OPERATION",
                    "details": {"state": "STALE"},
                }
            ]
        }
    )

    reconcile_responses: list[dict[str, Any]] = []
    original_reconcile = connection.reconcile_document_lease

    def tracked_reconcile(session_uuid: str, **kwargs: Any) -> dict[str, Any]:
        response = original_reconcile(session_uuid, **kwargs)
        reconcile_responses.append(response)
        return response

    results = loop.run_until_complete(
        orchestrator.recover_sessions(
            ("doc-d5",),
            STALE_RECOVERY_TRIGGER_HEARTBEAT,
            tracked_reconcile,
        )
    )
    assert results["doc-d5"].outcome == STALE_RECOVERY_OUTCOME_RECOVERED
    assert len(reconcile_calls) == 1
    _assert_never_saved_wire_observed(reconcile_calls[0], snapshot_id=snapshot_id)
    assert len(reconcile_responses) == 1
    response_state = reconcile_responses[0]["lease"]["document_state"]
    assert response_state["snapshot_id"] == snapshot_id
    assert response_state.get("baseline") in (None, "")
    assert reconcile_responses[0]["lease"]["document"]["canonical_path"] in (None, "")

    protected_calls = 0

    def protected_invoke_v2(
        method: str,
        params: dict[str, Any],
        _context: Any,
        *,
        control: bool = False,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        nonlocal protected_calls
        del params, control, timeout
        protected_calls += 1
        assert method == "edit_object"
        return _rpc_ok_response()

    with mock.patch.object(
        connection, "invoke_v2", side_effect=protected_invoke_v2
    ), mock.patch.object(
        connection,
        "invoke_rpc",
        return_value=_rpc_ok_response(),
    ):
        context = _request_context("doc-d5", "d5-secret")
        follow_up = connection.invoke_v2("edit_object", {"document": "Doc"}, context)

    assert _invoke_success(follow_up) is True
    assert protected_calls == 1
    assert snapshot_id is not None
    loop.close()


@pytest.mark.unit
def test_accelerated_timeout_sync_tool_heartbeat_and_post_tool_recovery(
    monkeypatch,
):
    """Long sync tool exceeds stale TTL while heartbeats stay healthy; no false recovery."""

    stale_after_s = 0.05
    orchestrator = StaleLeaseRecoveryOrchestrator(stale_after_seconds=stale_after_s)
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
                    "state": "LOCKED_IDLE",
                    "success": True,
                }
            ],
        },
    }
    connection.reconcile_document_lease.return_value = _lease_reconcile_wire_result(
        mode="dirty_saved",
    )

    server_instance = InstrumentedFastMCP("p7-accelerated-timeout")
    server_instance.post_tool_completed_hook = server._post_tool_stale_recovery
    started = threading.Event()
    release = threading.Event()
    heartbeat_calls = 0
    tool_started_monotonic = 0.0

    @server_instance.tool(name="slow_sync_probe")
    def slow_sync_probe() -> dict[str, str]:
        nonlocal tool_started_monotonic
        tool_started_monotonic = time.monotonic()
        started.set()
        if not release.wait(timeout=2.0):
            raise TimeoutError("slow_sync_probe was not released")
        return {"status": "done"}

    async def run_real_heartbeat_once() -> bool:
        nonlocal heartbeat_calls
        with mock.patch.object(server, "state") as state_mock, mock.patch.object(
            server, "stale_recovery", orchestrator
        ), mock.patch.object(server, "_authenticate_connection"), mock.patch.object(
            server, "_connection_lock"
        ):
            state_mock.lease_manager = manager
            state_mock.freecad_connection = connection
            successful = await server._lease_heartbeat_once()
        heartbeat_calls += 1
        return successful

    async def run() -> None:
        monkeypatch.setattr(
            "freecad_mcp.instrumented_server.emit_event",
            lambda *_args, **_kwargs: None,
        )
        monkeypatch.setattr(server_instance, "get_context", lambda: _mcp_context())
        with mock.patch.object(server, "state") as state_mock, mock.patch.object(
            server, "stale_recovery", orchestrator
        ):
            state_mock.lease_manager = manager
            state_mock.freecad_connection = connection

            tool_task = asyncio.create_task(
                server_instance.call_tool("slow_sync_probe", {})
            )
            deadline = time.monotonic() + 1.0
            while not started.is_set():
                if time.monotonic() >= deadline:
                    raise TimeoutError("slow_sync_probe did not start")
                await asyncio.sleep(0.005)

            tick_interval_s = stale_after_s / 4
            heartbeat_deadline = time.monotonic() + stale_after_s * 4
            while time.monotonic() < heartbeat_deadline:
                await run_real_heartbeat_once()
                await asyncio.sleep(tick_interval_s)

            assert heartbeat_calls >= 2
            assert (time.monotonic() - tool_started_monotonic) > stale_after_s

            release.set()
            await asyncio.wait_for(tool_task, timeout=2.0)

        connection.reconcile_document_lease.assert_not_called()
        assert connection.heartbeat_document_locks_batch.call_count >= 2
        assert heartbeat_calls >= 2

    asyncio.run(run())


@pytest.mark.unit
def test_concurrent_recovery_triggers_serialize_under_per_document_lock():
    """Heartbeat, post-tool, and pre-op triggers serialize to a single reconcile."""

    orchestrator = StaleLeaseRecoveryOrchestrator()
    reconcile_count = 0
    reconcile_started = threading.Event()
    reconcile_release = threading.Event()
    triggers_seen: list[str] = []
    lock = threading.Lock()

    def gated_reconcile(_session_uuid: str) -> dict[str, Any]:
        nonlocal reconcile_count
        with lock:
            reconcile_count += 1
            if reconcile_count > 1:
                raise AssertionError("more than one reconcile ran concurrently")
        reconcile_started.set()
        if not reconcile_release.wait(timeout=2.0):
            raise TimeoutError("reconcile gate was not released")
        return _lease_reconcile_wire_result(mode="clean")

    orchestrator.mark_needs_recovery("doc-a")

    async def heartbeat_recovery() -> None:
        results = await orchestrator.recover_sessions(
            ("doc-a",),
            STALE_RECOVERY_TRIGGER_HEARTBEAT,
            gated_reconcile,
        )
        triggers_seen.append(results["doc-a"].trigger)

    async def post_tool_recovery() -> None:
        results = await orchestrator.recover_sessions(
            ("doc-a",),
            STALE_RECOVERY_TRIGGER_POST_TOOL,
            gated_reconcile,
        )
        triggers_seen.append(results["doc-a"].trigger)

    async def run() -> None:
        orchestrator.bind_event_loop(asyncio.get_running_loop())
        connection = _configure_connection(orchestrator)

        def pre_operation_recovery() -> None:
            with mock.patch.object(
                connection, "reconcile_document_lease", side_effect=gated_reconcile
            ), mock.patch.object(
                connection,
                "invoke_rpc",
                return_value=_rpc_ok_response(),
            ):
                context = _request_context("doc-a", "secret-a")
                connection.invoke_v2("edit_object", {"document": "Doc"}, context)
            triggers_seen.append(STALE_RECOVERY_TRIGGER_PRE_OPERATION)

        heartbeat_task = asyncio.create_task(heartbeat_recovery())
        post_tool_task = asyncio.create_task(post_tool_recovery())
        pre_op_task = asyncio.create_task(asyncio.to_thread(pre_operation_recovery))

        deadline = time.monotonic() + 1.0
        while not reconcile_started.is_set():
            if time.monotonic() >= deadline:
                raise TimeoutError("reconcile never started")
            await asyncio.sleep(0.005)

        reconcile_release.set()
        await asyncio.gather(heartbeat_task, post_tool_task, pre_op_task)

        assert reconcile_count == 1
        assert len(triggers_seen) == 3
        assert orchestrator.sessions_needing_recovery(("doc-a",)) == ()

    asyncio.run(run())


@pytest.mark.unit
def test_recovered_lease_skips_redundant_pre_operation_reconcile():
    """After one trigger wins, later protected work observes an unnecessary skip."""

    orchestrator = StaleLeaseRecoveryOrchestrator()
    loop = asyncio.new_event_loop()
    connection = _configure_connection(orchestrator, loop=loop)
    reconcile_calls, _snapshot_id = _install_lease_reconcile_invoke_v2_stub(
        connection,
        session="doc-a",
        token="secret-a",
        dirty=False,
    )

    orchestrator.mark_needs_recovery("doc-a")

    first = loop.run_until_complete(
        orchestrator.recover_sessions(
            ("doc-a",),
            STALE_RECOVERY_TRIGGER_HEARTBEAT,
            connection.reconcile_document_lease,
        )
    )
    assert first["doc-a"].outcome == STALE_RECOVERY_OUTCOME_RECOVERED
    assert len(reconcile_calls) == 1

    second = loop.run_until_complete(
        orchestrator.recover_sessions(
            ("doc-a",),
            STALE_RECOVERY_TRIGGER_PRE_OPERATION,
            connection.reconcile_document_lease,
        )
    )
    assert second["doc-a"].outcome == STALE_RECOVERY_OUTCOME_SKIPPED_UNNECESSARY
    assert len(reconcile_calls) == 1

    with mock.patch.object(
        connection,
        "invoke_rpc",
        return_value=_rpc_ok_response(),
    ):
        context = _request_context("doc-a", "secret-a")
        response = connection.invoke_v2("edit_object", {"document": "Doc"}, context)

    assert _invoke_success(response) is True
    assert len(reconcile_calls) == 1
    loop.close()


@pytest.mark.unit
def test_rpc_refusal_recovery_redacts_credential_in_structured_response():
    orchestrator = StaleLeaseRecoveryOrchestrator()
    loop = asyncio.new_event_loop()
    connection = _configure_connection(
        orchestrator, token="raw-recovery-token", loop=loop
    )
    reconcile_calls, _snapshot_id = _install_lease_reconcile_invoke_v2_stub(
        connection,
        session="doc-a",
        token="raw-recovery-token",
        dirty=True,
    )

    with mock.patch.object(
        connection,
        "invoke_rpc",
        return_value={
            "ok": False,
            "error_code": "LEASE_STATE_FORBIDS_OPERATION",
            "details": {"state": "STALE"},
        },
    ):
        context = _request_context("doc-a", "raw-recovery-token")
        response = connection.invoke_v2("edit_object", {"document": "Doc"}, context)

    assert len(reconcile_calls) == 1
    _assert_dirty_saved_wire_observed(reconcile_calls[0])
    rendered = json.dumps(response, sort_keys=True)
    assert "raw-recovery-token" not in rendered
    assert response["stale_recovery_succeeded"] is True
    loop.close()
