"""Phase 17 contracts for sole-root startup and exact-once runtime shutdown."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP import runtime as runtime_module
from addon.FreeCADMCP.rpc_server import rpc_server, server_shutdown

pytestmark = pytest.mark.unit


class _Dispatcher:
    def __init__(self, calls):
        self.calls = calls

    def stop_accepting(self):
        self.calls.append("dispatcher:stop")

    def deleteLater(self):
        self.calls.append("dispatcher:delete")


class _Listener:
    def __init__(self, calls):
        self.calls = calls
        self.registered = []

    def register_instance(self, instance):
        self.registered.append(instance)

    def begin_shutdown(self):
        self.calls.append("listener:begin")

    def shutdown(self):
        self.calls.append("listener:shutdown")

    def server_close(self):
        self.calls.append("listener:close")


def test_runtime_disposal_unsubscribes_bridge_in_reverse_construction_order():
    calls = []
    dispatcher = _Dispatcher(calls)
    listener = _Listener(calls)
    bridge = SimpleNamespace(
        _dispose_runtime_bindings=lambda: calls.append("bridge:dispose")
    )

    runtime, warning = runtime_module._build_addon_runtime(
        shutdown_requested=threading.Event(),
        dispatcher_factory=lambda: dispatcher,
        worker_manager_factory=lambda _dispatcher: None,
        listener_factory=lambda _dispatcher, _bridge: listener,
        authentication_factory=lambda _listener, _replay: (None, ""),
        capability_bridge_factory=lambda *_args: bridge,
        authentication_required=False,
        request_replay_cache=object(),
        inflight_requests=object(),
    )

    assert warning == ""
    runtime.dispose()
    runtime.dispose()

    assert calls == [
        "listener:close",
        "bridge:dispose",
        "dispatcher:stop",
        "dispatcher:delete",
    ]


def test_disposed_runtime_tombstone_retains_only_restart_replay_state():
    replay_cache = object()
    shutdown_requested = threading.Event()
    runtime = runtime_module.AddonRuntime(
        listener=object(),
        dispatcher=object(),
        worker_manager=object(),
        session_manager=object(),
        request_replay_cache=replay_cache,
        inflight_requests=object(),
        collaboration_bridge=object(),
        shutdown_requested=shutdown_requested,
    )
    runtime.bind_publication(
        listener_thread=object(),
        runtime_manifest=object(),
        actual_endpoint={"host": "127.0.0.1", "port": 9875},
        runtime_id="runtime-id",
        server_started_at="2026-08-05T00:00:00Z",
    )

    runtime.dispose()

    assert runtime.disposed is True
    assert runtime.request_replay_cache is replay_cache
    assert runtime.shutdown_requested is shutdown_requested
    assert shutdown_requested.is_set()
    assert runtime._owned_resources == ()
    for name in (
        "listener",
        "dispatcher",
        "worker_manager",
        "session_manager",
        "inflight_requests",
        "collaboration_bridge",
        "listener_thread",
        "runtime_manifest",
        "actual_endpoint",
    ):
        assert getattr(runtime, name) is None
    assert runtime.runtime_id == ""
    assert runtime.server_started_at == ""


def test_disposal_failure_clears_auth_metadata_and_successful_resources():
    calls = []
    failure = RuntimeError("listener close failed")

    class _FailingListener(_Listener):
        def server_close(self):
            self.calls.append("listener:close")
            raise failure

    dispatcher = _Dispatcher(calls)
    listener = _FailingListener(calls)
    worker = SimpleNamespace(
        stop=lambda *, timeout: calls.append(("worker:stop", timeout)) or True
    )
    bridge = SimpleNamespace(
        _dispose_runtime_bindings=lambda: calls.append("bridge:dispose")
    )
    session = object()
    replay = object()
    runtime, _warning = runtime_module._build_addon_runtime(
        shutdown_requested=threading.Event(),
        dispatcher_factory=lambda: dispatcher,
        worker_manager_factory=lambda _dispatcher: worker,
        listener_factory=lambda _dispatcher, _bridge: listener,
        authentication_factory=lambda _listener, _replay: (session, ""),
        capability_bridge_factory=lambda *_args: bridge,
        authentication_required=True,
        request_replay_cache=replay,
        inflight_requests=object(),
    )
    runtime.bind_publication(
        listener_thread=object(),
        runtime_manifest=object(),
        actual_endpoint={"host": "127.0.0.1", "port": 9875},
        runtime_id="runtime-id",
        server_started_at="2026-08-05T00:00:00Z",
    )

    with pytest.raises(BaseExceptionGroup, match="disposal failed"):
        runtime.dispose()

    assert runtime.listener is listener
    assert runtime._owned_resources[0][0] is listener
    assert runtime.request_replay_cache is replay
    for name in (
        "dispatcher",
        "worker_manager",
        "session_manager",
        "inflight_requests",
        "collaboration_bridge",
        "listener_thread",
        "runtime_manifest",
        "actual_endpoint",
    ):
        assert getattr(runtime, name) is None
    assert runtime.runtime_id == ""
    assert runtime.server_started_at == ""
    assert calls == [
        "listener:close",
        "bridge:dispose",
        ("worker:stop", 4.0),
        "dispatcher:stop",
        "dispatcher:delete",
    ]


def _published_runtime(
    monkeypatch,
    *,
    calls,
    dispose,
    inflight_requests=None,
    bridge=None,
    listener=True,
    listener_thread=None,
):
    listener_value = _Listener(calls) if listener else None
    dispatcher = _Dispatcher(calls)
    session_manager = object()
    runtime = SimpleNamespace(
        listener=listener_value,
        dispatcher=dispatcher,
        worker_manager=None,
        session_manager=session_manager,
        request_replay_cache=object(),
        inflight_requests=inflight_requests,
        collaboration_bridge=bridge,
        listener_thread=listener_thread,
        runtime_manifest=None,
        actual_endpoint=None,
        runtime_id="",
        server_started_at="",
        shutdown_requested=threading.Event(),
        disposed=False,
    )

    def dispose_runtime():
        dispose()
        runtime.disposed = True
        runtime.listener = None
        runtime.dispatcher = None
        runtime.worker_manager = None
        runtime.session_manager = None
        runtime.inflight_requests = None
        runtime.collaboration_bridge = None

    runtime.dispose = dispose_runtime
    monkeypatch.setattr(rpc_server, "_runtime_lifecycle_lock", threading.RLock())
    monkeypatch.setattr(rpc_server, "_runtime_shutdown_claim", None)
    monkeypatch.setattr(rpc_server, "_addon_runtime", runtime)
    return runtime


@pytest.mark.parametrize("failure_stage", ["construction", "start"])
def test_runtime_disposal_thread_failure_falls_back_synchronously(
    monkeypatch, failure_stage
):
    calls = []
    runtime = _published_runtime(
        monkeypatch,
        calls=calls,
        dispose=lambda: calls.append("runtime:dispose"),
    )

    class _FailingCleanupThread:
        def start(self):
            calls.append("cleanup-thread:start")
            raise RuntimeError("cleanup thread start failed")

    def thread_factory(**_kwargs):
        calls.append("cleanup-thread:construct")
        if failure_stage == "construction":
            raise RuntimeError("cleanup thread construction failed")
        return _FailingCleanupThread()

    monkeypatch.setattr(
        server_shutdown,
        "threading",
        SimpleNamespace(Thread=thread_factory),
    )

    assert rpc_server.stop_rpc_server() == "RPC Server stopped."
    assert runtime.disposed is True
    assert rpc_server._runtime_shutdown_claim is None
    assert calls == [
        "cleanup-thread:construct",
        *(["cleanup-thread:start"] if failure_stage == "start" else []),
        "listener:begin",
        "listener:shutdown",
        "runtime:dispose",
    ]


def test_concurrent_stop_claims_and_disposes_one_runtime_exactly_once(monkeypatch):
    calls = []
    dispose_started = threading.Event()
    release_dispose = threading.Event()

    def dispose():
        calls.append("runtime:dispose")
        dispose_started.set()
        assert release_dispose.wait(1.0)

    runtime = _published_runtime(monkeypatch, calls=calls, dispose=dispose)
    results = []
    callers = [
        threading.Thread(target=lambda: results.append(rpc_server.stop_rpc_server()))
        for _index in range(2)
    ]

    callers[0].start()
    assert dispose_started.wait(1.0)
    callers[1].start()
    time.sleep(0.02)
    assert rpc_server._addon_runtime is runtime
    assert rpc_server._runtime_shutdown_claim is not None
    release_dispose.set()
    for caller in callers:
        caller.join(timeout=1.0)

    assert sorted(results) == ["RPC Server stopped.", "RPC Server stopped."]
    assert calls == [
        "listener:begin",
        "listener:shutdown",
        "runtime:dispose",
    ]
    assert rpc_server._addon_runtime is runtime
    assert runtime.disposed is True
    assert runtime.request_replay_cache is not None
    assert rpc_server._runtime_shutdown_claim is None
    assert rpc_server.rpc_session_manager is None
    assert rpc_server.rpc_runtime_manifest is None


def test_shutdown_uses_composed_bridge_and_accepts_partial_runtime(monkeypatch):
    calls = []
    request = SimpleNamespace(request_id="request-1")
    registry = SimpleNamespace(request_cancel_all=lambda: [request])
    bridge = SimpleNamespace(
        _begin_request_cancellation=lambda current, *, wait_timeout: calls.append(
            ("cancel", current, wait_timeout)
        )
        or []
    )
    _published_runtime(
        monkeypatch,
        calls=calls,
        dispose=lambda: calls.append("runtime:dispose"),
        inflight_requests=registry,
        bridge=bridge,
        listener=False,
    )
    monkeypatch.setattr(
        rpc_server,
        "FreeCADRPC",
        lambda: pytest.fail("shutdown must use the composed bridge"),
    )

    assert rpc_server.stop_rpc_server() == "RPC Server stopped."
    assert calls[0][0:2] == ("cancel", request)
    assert 0.0 <= calls[0][2] <= rpc_server.RPC_SHUTDOWN_CANCELLATION_WAIT_SECONDS
    assert calls[1] == "runtime:dispose"


def test_shutdown_quiesces_workers_before_listener_disposal(monkeypatch):
    calls = []
    worker_quiesced = threading.Event()

    class _Worker:
        def _begin_shutdown(self):
            calls.append("worker:begin")
            worker_quiesced.set()

        def stop(self, *, timeout):
            assert worker_quiesced.is_set()
            calls.append(("worker:stop", timeout))
            return True

    class _WaitingListener(_Listener):
        def server_close(self):
            assert worker_quiesced.is_set()
            super().server_close()

    worker = _Worker()
    listener = _WaitingListener(calls)
    dispatcher = _Dispatcher(calls)
    bridge = SimpleNamespace(
        _dispose_runtime_bindings=lambda: calls.append("bridge:dispose")
    )
    runtime, _warning = runtime_module._build_addon_runtime(
        shutdown_requested=threading.Event(),
        dispatcher_factory=lambda: dispatcher,
        worker_manager_factory=lambda _dispatcher: worker,
        listener_factory=lambda _dispatcher, _bridge: listener,
        authentication_factory=lambda _listener, _replay: (None, ""),
        capability_bridge_factory=lambda *_args: bridge,
        authentication_required=False,
        request_replay_cache=object(),
        inflight_requests=SimpleNamespace(request_cancel_all=lambda: ()),
    )
    monkeypatch.setattr(rpc_server, "_runtime_lifecycle_lock", threading.RLock())
    monkeypatch.setattr(rpc_server, "_runtime_shutdown_claim", None)
    monkeypatch.setattr(rpc_server, "_addon_runtime", runtime)

    assert rpc_server.stop_rpc_server(wait_for_completion=True) == "RPC Server stopped."
    assert calls == [
        "listener:begin",
        "listener:shutdown",
        "worker:begin",
        "listener:close",
        "bridge:dispose",
        ("worker:stop", 4.0),
        "dispatcher:stop",
        "dispatcher:delete",
    ]


def test_cancellation_failure_retains_shutdown_claim_and_blocks_restart(
    monkeypatch,
):
    calls = []
    failure = RuntimeError("cancellation registry failed")
    registry = SimpleNamespace(
        request_cancel_all=lambda: (_ for _ in ()).throw(failure)
    )
    runtime = _published_runtime(
        monkeypatch,
        calls=calls,
        dispose=lambda: calls.append("runtime:dispose"),
        inflight_requests=registry,
        bridge=object(),
    )

    result = rpc_server.stop_rpc_server()
    claim = rpc_server._runtime_shutdown_claim

    assert result.startswith("RPC Server shutdown failed:")
    assert claim is not None
    assert claim.runtime is runtime
    assert failure in claim.failure.exceptions
    assert claim.completed.is_set()
    assert calls[-1] == "runtime:dispose"
    assert rpc_server.start_rpc_server() == "RPC Server shutdown is still in progress."


def test_bridge_disposal_drops_authentication_without_native_authority_changes():
    collaboration = rpc_server._build_collaboration_collaborators()
    execution = rpc_server._build_execution_collaborators(
        compatibility_api=collaboration.compatibility_api
    )
    facade = rpc_server.FreeCADRPC(
        collaboration_collaborators=collaboration,
        execution_collaborators=execution,
    )
    native_api = facade._collaboration_collaborators.compatibility_api
    manifest = object()
    session_manager = object()
    endpoint = {"host": "127.0.0.1", "port": 9875}

    facade._bind_collaboration_runtime_manifest(manifest)
    facade._bind_authenticated_execution_runtime(
        session_manager=session_manager,
        runtime_manifest=manifest,
        actual_endpoint=endpoint,
        server_started_at="2026-08-05T00:00:00Z",
    )
    facade._dispose_runtime_bindings()
    facade._dispose_runtime_bindings()

    assert facade._collaboration_collaborators.runtime_manifest is None
    assert facade._execution_collaborators.session_manager is None
    assert facade._execution_collaborators.runtime_manifest is None
    assert facade._execution_collaborators.actual_endpoint is None
    assert facade._execution_collaborators.server_started_at == ""
    assert facade._collaboration_collaborators.compatibility_api is native_api
    assert not hasattr(
        facade._collaboration_collaborators,
        "document_lease_service",
    )


def test_start_refuses_while_prior_runtime_shutdown_is_in_progress(monkeypatch):
    monkeypatch.setattr(rpc_server, "_runtime_shutdown_claim", threading.Event())
    monkeypatch.setattr(rpc_server, "_addon_runtime", None)
    assert rpc_server.start_rpc_server() == "RPC Server shutdown is still in progress."


def test_shutdown_failure_retains_exact_runtime_claim_and_blocks_restart(monkeypatch):
    calls = []
    failure = RuntimeError("listener disposal failed")

    def fail_dispose():
        calls.append("runtime:dispose")
        raise failure

    runtime = _published_runtime(monkeypatch, calls=calls, dispose=fail_dispose)

    first = rpc_server.stop_rpc_server()
    claim = rpc_server._runtime_shutdown_claim
    second = rpc_server.stop_rpc_server()

    assert first.startswith("RPC Server shutdown failed:")
    assert second == first
    assert rpc_server._addon_runtime is runtime
    assert claim is not None
    assert claim.runtime is runtime
    assert claim.completed.is_set()
    assert claim.failure is not None
    assert calls.count("runtime:dispose") == 1
    assert rpc_server.start_rpc_server() == "RPC Server shutdown is still in progress."


def test_listener_thread_timeout_retains_claim_and_blocks_restart(monkeypatch):
    calls = []

    class _StuckThread:
        def join(self, *, timeout):
            calls.append(("thread:join", timeout))

        def is_alive(self):
            return True

    listener_thread = _StuckThread()
    runtime = _published_runtime(
        monkeypatch,
        calls=calls,
        dispose=lambda: calls.append("runtime:dispose"),
        listener_thread=listener_thread,
    )

    result = rpc_server.stop_rpc_server()
    claim = rpc_server._runtime_shutdown_claim

    assert result.startswith("RPC Server shutdown failed:")
    assert rpc_server._addon_runtime is runtime
    assert claim is not None
    assert any(
        "listener thread did not stop" in str(failure)
        for failure in claim.failure.exceptions
    )
    assert claim.runtime is runtime
    assert claim.listener_thread is listener_thread
    assert claim.completed.is_set()
    assert calls == [
        "listener:begin",
        "listener:shutdown",
        ("thread:join", 2.0),
        "runtime:dispose",
    ]
    assert rpc_server.start_rpc_server() == "RPC Server shutdown is still in progress."


def test_final_shutdown_waits_for_runtime_disposal_before_returning(monkeypatch):
    calls = []
    dispose_started = threading.Event()
    release_dispose = threading.Event()

    def dispose():
        calls.append("runtime:dispose")
        dispose_started.set()
        assert release_dispose.wait(1.0)

    _published_runtime(monkeypatch, calls=calls, dispose=dispose)
    results = []
    caller = threading.Thread(
        target=lambda: results.append(
            rpc_server.stop_rpc_server(wait_for_completion=True)
        )
    )
    caller.start()

    assert dispose_started.wait(1.0)
    assert results == []
    release_dispose.set()
    caller.join(timeout=1.0)

    assert results == ["RPC Server stopped."]
    assert rpc_server._runtime_shutdown_claim is None


def test_original_lifecycle_modules_remain_call_compatible(monkeypatch):
    from addon.FreeCADMCP.rpc_server import server_lifecycle, server_shutdown

    observed = []
    monkeypatch.setattr(
        server_lifecycle,
        "_compatibility_start",
        lambda port: observed.append(("start", port)) or "started",
    )
    monkeypatch.setattr(
        server_shutdown,
        "_compatibility_stop",
        lambda: observed.append(("stop", None)) or "stopped",
    )

    assert server_lifecycle.start_rpc_server(4321) == "started"
    assert server_shutdown.stop_rpc_server() == "stopped"
    assert observed == [("start", 4321), ("stop", None)]


def test_runtime_root_does_not_publish_retired_document_authority() -> None:
    for name in (
        "document_identity_service",
        "document_lease_service",
        "initialize_document_lease_runtime",
        "lease_watchdog_thread",
        "save_service",
    ):
        assert not hasattr(rpc_server, name)


def test_manual_start_stop_commands_use_exact_injected_root_callbacks():
    from addon.FreeCADMCP.rpc_server.commands_types.dependencies import (
        CommandDependencies,
    )
    from addon.FreeCADMCP.rpc_server.commands_types.start_rpc_server_command import (
        StartRPCServerCommand,
    )
    from addon.FreeCADMCP.rpc_server.commands_types.stop_rpc_server_command import (
        StopRPCServerCommand,
    )

    calls = []
    messages = []
    dependencies = CommandDependencies(
        freecad=SimpleNamespace(
            Console=SimpleNamespace(PrintMessage=messages.append)
        ),
        load_settings=dict,
        save_settings=lambda _settings: None,
        start_rpc_server=lambda: calls.append("start") or "started",
        stop_rpc_server=lambda: calls.append("stop") or "stopped",
        runtime_running=lambda: False,
    )
    StartRPCServerCommand(dependencies).Activated()
    StopRPCServerCommand(dependencies).Activated()

    assert calls == ["start", "stop"]
    assert messages == ["started\n", "stopped\n"]
