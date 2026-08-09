"""Behavior contracts for the Phase 11 add-on composition root."""

from __future__ import annotations

import importlib
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


class _ConstructionFailure(BaseException):
    """A fatal construction failure that must not escape partial cleanup."""


class _CleanupFailure(BaseException):
    """A fatal cleanup failure that must not hide construction failure."""


class _LaunchFailure(BaseException):
    """A fatal publication or launch failure that must survive rollback."""


class _TracingShutdown(threading.Event):
    def __init__(self, timeline: list[str]) -> None:
        super().__init__()
        self._timeline = timeline

    def set(self) -> None:
        self._timeline.append("shutdown")
        super().set()


class _BuildHarness:
    def __init__(
        self,
        *,
        fail_stage: str | None = None,
        primary: BaseException | None = None,
        session_manager: object | None = None,
        warning: str = "",
        cleanup_failures: dict[str, BaseException] | None = None,
    ) -> None:
        self.timeline: list[str] = []
        self.fail_stage = fail_stage
        self.primary = primary or _ConstructionFailure("construction failed")
        self.session_manager = object() if session_manager is None else session_manager
        self.warning = warning
        self.cleanup_failures = cleanup_failures or {}
        self.shutdown_requested = _TracingShutdown(self.timeline)

        self.request_replay_cache = object()
        self.inflight_requests = object()
        self.dispatcher = _BuildDispatcher(self)
        self.worker_manager = _BuildWorkerManager(self)
        self.capability_bridge = object()
        self.listener = _BuildListener(self)

    def reach(self, stage: str) -> None:
        self.timeline.append(f"construct:{stage}")
        if self.fail_stage == stage:
            raise self.primary

    def cleanup(self, component: str) -> None:
        self.timeline.append(f"cleanup:{component}")
        failure = self.cleanup_failures.get(component)
        if failure is not None:
            raise failure

    def dispatcher_factory(self) -> object:
        self.reach("dispatcher")
        return self.dispatcher

    def worker_manager_factory(self, dispatcher: object) -> object:
        assert dispatcher is self.dispatcher
        self.reach("worker_manager")
        return self.worker_manager

    def capability_bridge_factory(
        self,
        dispatcher: object,
        worker_manager: object,
        request_replay_cache: object,
        inflight_requests: object,
    ) -> object:
        assert dispatcher is self.dispatcher
        assert worker_manager is self.worker_manager
        assert request_replay_cache is self.request_replay_cache
        assert inflight_requests is self.inflight_requests
        self.reach("capability_bridge")
        return self.capability_bridge

    def listener_factory(self, dispatcher: object, capability_bridge: object) -> object:
        assert dispatcher is self.dispatcher
        assert capability_bridge is self.capability_bridge
        self.reach("listener")
        return self.listener

    def authentication_factory(
        self, listener: object, request_replay_cache: object
    ) -> tuple[object | None, str]:
        assert listener is self.listener
        assert request_replay_cache is self.request_replay_cache
        self.reach("authentication")
        return self.session_manager, self.warning

    def build(self, runtime_module: Any, *, authentication_required: bool = True):
        return runtime_module._build_addon_runtime(
            shutdown_requested=self.shutdown_requested,
            dispatcher_factory=self.dispatcher_factory,
            worker_manager_factory=self.worker_manager_factory,
            listener_factory=self.listener_factory,
            authentication_factory=self.authentication_factory,
            capability_bridge_factory=self.capability_bridge_factory,
            authentication_required=authentication_required,
            request_replay_cache=self.request_replay_cache,
            inflight_requests=self.inflight_requests,
        )


class _BuildDispatcher:
    def __init__(self, harness: _BuildHarness) -> None:
        self._harness = harness

    def deleteLater(self) -> None:
        self._harness.cleanup("dispatcher")

    def start(self) -> None:  # pragma: no cover - must remain uncalled
        self._harness.timeline.append("start:dispatcher")


class _BuildWorkerManager:
    def __init__(self, harness: _BuildHarness) -> None:
        self._harness = harness

    def stop(self, timeout: float = 4.0) -> bool:
        assert timeout == 4.0
        self._harness.cleanup("worker_manager")
        return True

    def start(self) -> None:  # pragma: no cover - must remain uncalled
        self._harness.timeline.append("start:worker_manager")


class _BuildListener:
    def __init__(self, harness: _BuildHarness) -> None:
        self._harness = harness
        self.registered: list[object] = []

    def register_instance(self, instance: object) -> None:
        assert instance is self._harness.capability_bridge
        self._harness.reach("register_instance")
        self.registered.append(instance)

    def server_close(self) -> None:
        self._harness.cleanup("listener")

    def serve_forever(self) -> None:  # pragma: no cover - must remain uncalled
        self._harness.timeline.append("serve:listener")

    def start(self) -> None:  # pragma: no cover - must remain uncalled
        self._harness.timeline.append("start:listener")


def _runtime_module(monkeypatch, module_name: str):
    if module_name == "runtime":
        addon_root = str(Path(__file__).resolve().parents[1] / "addon" / "FreeCADMCP")
        monkeypatch.syspath_prepend(addon_root)
        monkeypatch.delitem(sys.modules, "runtime", raising=False)
    return importlib.import_module(module_name)


@pytest.mark.parametrize("module_name", ["addon.FreeCADMCP.runtime", "runtime"])
def test_builder_wires_exact_dependencies_without_starting_components(
    monkeypatch, module_name: str
) -> None:
    runtime_module = _runtime_module(monkeypatch, module_name)
    session_manager = object()
    harness = _BuildHarness(
        session_manager=session_manager,
        warning=" authentication warning",
    )

    runtime, warning = harness.build(runtime_module)

    assert warning == " authentication warning"
    assert runtime.shutdown_requested is harness.shutdown_requested
    assert runtime.dispatcher is harness.dispatcher
    assert runtime.worker_manager is harness.worker_manager
    assert runtime.listener is harness.listener
    assert runtime.session_manager is session_manager
    assert runtime.request_replay_cache is harness.request_replay_cache
    assert runtime.inflight_requests is harness.inflight_requests
    assert runtime.collaboration_bridge is harness.capability_bridge
    assert harness.listener.registered == [harness.capability_bridge]
    assert harness.timeline == [
        "construct:dispatcher",
        "construct:worker_manager",
        "construct:capability_bridge",
        "construct:listener",
        "construct:register_instance",
        "construct:authentication",
    ]
    assert not any(event.startswith(("start:", "serve:")) for event in harness.timeline)

    runtime.dispose()

    assert harness.timeline[-4:] == [
        "shutdown",
        "cleanup:listener",
        "cleanup:worker_manager",
        "cleanup:dispatcher",
    ]


def test_optional_authentication_retains_warning_and_none_session() -> None:
    runtime_module = importlib.import_module("addon.FreeCADMCP.runtime")
    harness = _BuildHarness(session_manager=object(), warning=" optional warning")
    harness.session_manager = None

    runtime, warning = harness.build(
        runtime_module,
        authentication_required=False,
    )

    assert runtime.session_manager is None
    assert warning == " optional warning"
    runtime.dispose()


def test_required_authentication_rejects_none_and_cleans_partial_graph() -> None:
    runtime_module = importlib.import_module("addon.FreeCADMCP.runtime")
    harness = _BuildHarness(session_manager=object())
    harness.session_manager = None

    with pytest.raises(RuntimeError, match="authenticat"):
        harness.build(runtime_module, authentication_required=True)

    assert harness.shutdown_requested.is_set()
    assert harness.timeline[-4:] == [
        "shutdown",
        "cleanup:listener",
        "cleanup:worker_manager",
        "cleanup:dispatcher",
    ]


@pytest.mark.parametrize(
    ("fail_stage", "expected_cleanup"),
    [
        ("dispatcher", []),
        ("worker_manager", ["dispatcher"]),
        ("capability_bridge", ["worker_manager", "dispatcher"]),
        ("listener", ["worker_manager", "dispatcher"]),
        (
            "register_instance",
            ["listener", "worker_manager", "dispatcher"],
        ),
        ("authentication", ["listener", "worker_manager", "dispatcher"]),
    ],
)
def test_construction_failure_signals_shutdown_and_cleans_reverse_exactly_once(
    fail_stage: str,
    expected_cleanup: list[str],
) -> None:
    runtime_module = importlib.import_module("addon.FreeCADMCP.runtime")
    primary = _ConstructionFailure(f"failed at {fail_stage}")
    harness = _BuildHarness(fail_stage=fail_stage, primary=primary)

    with pytest.raises(_ConstructionFailure) as captured:
        harness.build(runtime_module)

    assert captured.value is primary
    assert harness.shutdown_requested.is_set()
    shutdown_index = harness.timeline.index("shutdown")
    cleanup = [
        event.removeprefix("cleanup:")
        for event in harness.timeline[shutdown_index + 1 :]
    ]
    assert cleanup == expected_cleanup
    assert len(cleanup) == len(set(cleanup))


def test_construction_cleanup_groups_primary_and_all_fatal_cleanup_failures() -> None:
    runtime_module = importlib.import_module("addon.FreeCADMCP.runtime")
    primary = _ConstructionFailure("authentication exploded")
    listener_failure = _CleanupFailure("listener close exploded")
    worker_failure = _CleanupFailure("worker stop exploded")
    dispatcher_failure = _CleanupFailure("dispatcher release exploded")
    harness = _BuildHarness(
        fail_stage="authentication",
        primary=primary,
        cleanup_failures={
            "listener": listener_failure,
            "worker_manager": worker_failure,
            "dispatcher": dispatcher_failure,
        },
    )

    with pytest.raises(BaseExceptionGroup) as captured:
        harness.build(runtime_module)

    def leaves(error: BaseException) -> tuple[BaseException, ...]:
        if isinstance(error, BaseExceptionGroup):
            return tuple(leaf for nested in error.exceptions for leaf in leaves(nested))
        return (error,)

    assert leaves(captured.value) == (
        primary,
        listener_failure,
        worker_failure,
        dispatcher_failure,
    )
    assert harness.timeline[-4:] == [
        "shutdown",
        "cleanup:listener",
        "cleanup:worker_manager",
        "cleanup:dispatcher",
    ]


def test_worker_stop_timeout_is_reported_after_all_runtime_cleanup() -> None:
    runtime_module = importlib.import_module("addon.FreeCADMCP.runtime")
    harness = _BuildHarness()

    def incomplete_stop(*, timeout: float) -> bool:
        assert timeout == 4.0
        harness.cleanup("worker_manager")
        return False

    harness.worker_manager.stop = incomplete_stop
    runtime, _warning = harness.build(runtime_module)

    with pytest.raises(BaseExceptionGroup, match="disposal failed") as captured:
        runtime.dispose()

    assert "did not stop" in str(captured.value.exceptions[0])
    assert harness.timeline[-4:] == [
        "shutdown",
        "cleanup:listener",
        "cleanup:worker_manager",
        "cleanup:dispatcher",
    ]


class _LiveDispatcher:
    def __init__(self, timeline: list[str], parent: object) -> None:
        self.timeline = timeline
        self.parent = parent
        self.cleanup_calls = 0

    def deleteLater(self) -> None:
        self.cleanup_calls += 1
        self.timeline.append("cleanup:dispatcher")


class _LiveWorkerManager:
    def __init__(self, timeline: list[str]) -> None:
        self.timeline = timeline
        self.cleanup_calls = 0
        self.start_calls = 0

    def _start(self) -> None:
        self.start_calls += 1
        self.timeline.append("start:worker_manager")

    def stop(self, timeout: float = 4.0) -> bool:
        assert timeout == 4.0
        self.cleanup_calls += 1
        self.timeline.append("cleanup:worker_manager")
        return True


class _LiveListener:
    server_address = ("127.0.0.1", 19875)

    def __init__(self, timeline: list[str]) -> None:
        self.timeline = timeline
        self.registered: list[object] = []
        self.cleanup_calls = 0

    def register_instance(self, instance: object) -> None:
        self.timeline.append("register:bridge")
        self.registered.append(instance)

    def serve_forever(self) -> None:
        self.timeline.append("serve:listener")

    def server_close(self) -> None:
        self.cleanup_calls += 1
        self.timeline.append("cleanup:listener")


def _prepare_live_start(
    monkeypatch,
    *,
    authentication_enabled: bool = False,
    bridge_failure: BaseException | None = None,
    listener_address: object = ("127.0.0.1", 19875),
    manifest_binding_failure: BaseException | None = None,
    thread_start_failure: BaseException | None = None,
):
    from addon.FreeCADMCP import runtime as runtime_module
    from addon.FreeCADMCP.rpc_server import rpc_server, server_lifecycle

    timeline: list[str] = []
    counts = {
        "builder": 0,
        "dispatcher": 0,
        "worker_manager": 0,
        "listener": 0,
        "bridge": 0,
        "thread": 0,
    }
    app_thread = object()
    parent = object()
    replay = SimpleNamespace()
    inflight = SimpleNamespace(request_cancel_all=list)
    session_manager = object()
    runtime_manifest = object()
    dispatcher = _LiveDispatcher(timeline, parent)
    worker_manager = _LiveWorkerManager(timeline)
    listener = _LiveListener(timeline)
    listener.server_address = listener_address
    bridge = SimpleNamespace(
        _collaboration_collaborators=None,
        _lifecycle_collaborators=None,
        _execution_collaborators=None,
        _cad_collaborators=None,
        _gui_collaborators=None,
    )

    def bind_collaboration_runtime_manifest(manifest):
        if manifest_binding_failure is not None:
            raise manifest_binding_failure
        bridge._collaboration_collaborators = (
            bridge._collaboration_collaborators.with_runtime_manifest(manifest)
        )

    bridge._bind_collaboration_runtime_manifest = bind_collaboration_runtime_manifest

    def bind_authenticated_execution_runtime(**kwargs):
        bridge._execution_collaborators = (
            bridge._execution_collaborators.with_authenticated_runtime(**kwargs)
        )

    bridge._bind_authenticated_execution_runtime = (
        bind_authenticated_execution_runtime
    )
    built: dict[str, object] = {}
    shutdown_requested = _TracingShutdown(timeline)

    real_builder = runtime_module._build_addon_runtime

    def tracked_builder(**kwargs):
        counts["builder"] += 1
        timeline.append("builder:called")
        result = real_builder(**kwargs)
        built["runtime"] = result[0]
        timeline.append("builder:return")
        return result

    def dispatcher_constructor(actual_parent):
        counts["dispatcher"] += 1
        timeline.append("factory:dispatcher")
        assert actual_parent is parent
        return dispatcher

    def worker_constructor(*_args, **kwargs):
        counts["worker_manager"] += 1
        timeline.append("factory:worker_manager")
        assert kwargs["autostart"] is False
        return worker_manager

    def listener_constructor(*_args, **_kwargs):
        counts["listener"] += 1
        timeline.append("factory:listener")
        return listener

    def bridge_constructor(*_args, **kwargs):
        counts["bridge"] += 1
        timeline.append("factory:bridge")
        if bridge_failure is not None:
            raise bridge_failure
        collaborators = kwargs["collaboration_collaborators"]
        lifecycle = kwargs["lifecycle_collaborators"]
        execution = kwargs["execution_collaborators"]
        cad = kwargs["cad_collaborators"]
        gui = kwargs["gui_collaborators"]
        assert _args == ()
        assert kwargs["allow_execute_code"] is True
        assert collaborators.inflight_request_registry is inflight
        for retired_name in (
            "document_lease_service",
            "document_identity_service",
            "handoff_continuation_store",
            "acquisition_claim_store",
        ):
            assert not hasattr(collaborators, retired_name)
        assert collaborators.request_replay_cache is replay
        assert collaborators.rpc_server_runtime_id == rpc_server._ADDON_RUNTIME_ID
        assert collaborators.runtime_manifest is None
        assert (
            collaborators.compatibility_api._document_lookup
            is rpc_server.FreeCAD.getDocument
        )
        assert lifecycle.freecad is rpc_server.FreeCAD
        assert not hasattr(lifecycle, "document_lease_service")
        assert not hasattr(lifecycle, "document_identity_service")
        assert not hasattr(lifecycle, "save_service")
        assert execution.compatibility_api is collaborators.compatibility_api
        assert execution.gui_dispatcher is dispatcher
        assert execution.worker_manager is worker_manager
        assert execution.request_replay_cache is replay
        assert execution.inflight_request_registry is inflight
        assert not hasattr(execution, "handoff_continuation_store")
        assert not hasattr(execution, "acquisition_claim_store")
        assert execution.runtime_id == rpc_server._ADDON_RUNTIME_ID
        assert execution.session_manager is None
        assert execution.runtime_manifest is None
        assert execution.actual_endpoint is None
        assert execution.server_started_at == ""
        assert cad.compatibility_api is collaborators.compatibility_api
        assert cad.freecad is rpc_server.FreeCAD
        assert gui.freecad is rpc_server.FreeCAD
        bridge._collaboration_collaborators = collaborators
        bridge._lifecycle_collaborators = lifecycle
        bridge._execution_collaborators = execution
        bridge._cad_collaborators = cad
        bridge._gui_collaborators = gui
        return bridge

    class _Thread:
        def __init__(self, *, target, daemon):
            counts["thread"] += 1
            self.target = target
            self.daemon = daemon
            timeline.append("thread:constructed")

        def start(self) -> None:
            timeline.append("thread:start")
            current_runtime = rpc_server._addon_runtime
            assert current_runtime is None or current_runtime.disposed
            assert rpc_server.rpc_server_instance is None
            assert rpc_server.gui_dispatcher is None
            assert rpc_server.worker_manager is None
            assert rpc_server.rpc_session_manager is None
            assert listener.registered[-1] is bridge
            if thread_start_failure is not None:
                raise thread_start_failure

        def join(self, *, timeout) -> None:
            assert timeout == 2.0

        def is_alive(self) -> bool:
            return False

    monkeypatch.setattr(runtime_module, "_build_addon_runtime", tracked_builder)
    monkeypatch.setattr(rpc_server, "_addon_runtime", None, raising=False)
    monkeypatch.setattr(rpc_server, "_runtime_shutdown_claim", None, raising=False)
    monkeypatch.setattr(rpc_server, "ShutdownEvent", lambda: shutdown_requested)
    monkeypatch.setattr(rpc_server, "RequestReplayCache", lambda: replay)
    monkeypatch.setattr(rpc_server, "InflightRequestRegistry", lambda: inflight)
    monkeypatch.setattr(
        rpc_server,
        "QtWidgets",
        SimpleNamespace(
            QApplication=SimpleNamespace(
                instance=lambda: SimpleNamespace(thread=lambda: app_thread)
            )
        ),
    )
    monkeypatch.setattr(
        rpc_server,
        "QtCore",
        SimpleNamespace(QThread=SimpleNamespace(currentThread=lambda: app_thread)),
    )
    monkeypatch.setattr(
        rpc_server,
        "FreeCADGui",
        SimpleNamespace(getMainWindow=lambda: parent),
    )
    monkeypatch.setattr(rpc_server, "GuiDispatcher", dispatcher_constructor)
    monkeypatch.setattr(rpc_server, "WorkerManager", worker_constructor)
    monkeypatch.setattr(rpc_server, "FilteredXMLRPCServer", listener_constructor)
    monkeypatch.setattr(rpc_server, "FreeCADRPC", bridge_constructor)
    monkeypatch.setattr(
        rpc_server,
        "threading",
        SimpleNamespace(Thread=_Thread, Event=threading.Event),
    )
    monkeypatch.setattr(
        rpc_server,
        "load_settings",
        lambda: {
            "document_lease_mode": "off",
            "rpc_port": 0,
            "remote_enabled": False,
            "allowed_ips": "127.0.0.1",
            "profile_instance_id": "profile" if authentication_enabled else "",
            "auth_secret_file": "secret" if authentication_enabled else "",
        },
    )
    monkeypatch.setattr(rpc_server, "configure_parts_library_path", lambda _path: None)
    monkeypatch.setattr(
        rpc_server, "_freecad_version_parts", lambda: ("1", "0", "0", "r")
    )
    monkeypatch.setattr(
        server_lifecycle,
        "FreeCAD",
        SimpleNamespace(getUserAppDataDir=lambda: "", getHomePath=lambda: ""),
    )
    monkeypatch.setattr(
        rpc_server, "resolve_rpc_bind_host", lambda _settings: "127.0.0.1"
    )
    if authentication_enabled:
        def construct_session_manager(*, manifest, secret):
            assert manifest is runtime_manifest
            assert secret == b"secret"
            assert rpc_server.rpc_server_instance is None
            assert rpc_server.rpc_session_manager is None
            assert rpc_server.rpc_runtime_manifest is None
            timeline.append("construct:session_manager")
            return session_manager

        monkeypatch.setattr(rpc_server, "SessionManager", construct_session_manager)
        monkeypatch.setattr(rpc_server, "load_profile_secret", lambda _path: b"secret")
        monkeypatch.setattr(
            rpc_server,
            "make_runtime_manifest",
            lambda **_kwargs: runtime_manifest,
        )
        monkeypatch.setattr(rpc_server, "_profile_fingerprint", lambda: "fingerprint")
    else:
        monkeypatch.setattr(
            rpc_server,
            "SessionManager",
            lambda **_kwargs: pytest.fail("optional authentication must stay disabled"),
        )
        monkeypatch.setattr(
            rpc_server,
            "load_profile_secret",
            lambda _path: pytest.fail("optional authentication must not load a secret"),
        )

    return SimpleNamespace(
        rpc_server=rpc_server,
        timeline=timeline,
        counts=counts,
        built=built,
        dispatcher=dispatcher,
        worker_manager=worker_manager,
        listener=listener,
        bridge=bridge,
        replay=replay,
        inflight=inflight,
        session_manager=session_manager,
        runtime_manifest=runtime_manifest,
    )


def test_runtime_start_builds_once_and_publishes_only_after_thread_start(
    monkeypatch,
) -> None:
    context = _prepare_live_start(monkeypatch)

    result = context.rpc_server.start_rpc_server()

    assert result == "RPC Server started at 127.0.0.1:19875."
    assert context.counts == {
        "builder": 1,
        "dispatcher": 1,
        "worker_manager": 1,
        "listener": 1,
        "bridge": 1,
        "thread": 1,
    }
    runtime = context.built["runtime"]
    assert context.rpc_server._addon_runtime is runtime
    assert context.rpc_server.rpc_server_runtime_id == context.rpc_server._ADDON_RUNTIME_ID
    assert (
        context.bridge._execution_collaborators.runtime_id
        == context.rpc_server._ADDON_RUNTIME_ID
    )
    assert runtime.listener is context.listener
    assert runtime.dispatcher is context.dispatcher
    assert runtime.worker_manager is context.worker_manager
    assert runtime.collaboration_bridge is context.bridge
    assert runtime.request_replay_cache is context.replay
    assert runtime.inflight_requests is context.inflight
    assert context.listener.registered == [context.bridge]
    assert context.timeline.index("builder:return") < context.timeline.index(
        "start:worker_manager"
    )
    assert context.timeline.index("start:worker_manager") < context.timeline.index(
        "thread:start"
    )
    assert "serve:listener" not in context.timeline
    runtime.dispose()


def test_repeated_start_reuses_the_one_published_runtime(monkeypatch) -> None:
    context = _prepare_live_start(monkeypatch)

    first = context.rpc_server.start_rpc_server()
    second = context.rpc_server.start_rpc_server()

    assert "started" in first.lower()
    assert second == "RPC Server already running."
    assert context.counts["builder"] == 1
    assert context.counts["thread"] == 1
    assert context.worker_manager.start_calls == 1
    context.built["runtime"].dispose()


def test_concurrent_start_constructs_and_publishes_one_runtime(monkeypatch) -> None:
    context = _prepare_live_start(monkeypatch)
    ready = threading.Barrier(3)
    results = []

    def start():
        ready.wait()
        results.append(context.rpc_server.start_rpc_server())

    callers = [threading.Thread(target=start) for _index in range(2)]
    for caller in callers:
        caller.start()
    ready.wait()
    for caller in callers:
        caller.join(timeout=1.0)

    assert sorted(results) == [
        "RPC Server already running.",
        "RPC Server started at 127.0.0.1:19875.",
    ]
    assert context.counts["builder"] == 1
    assert context.counts["thread"] == 1
    context.built["runtime"].dispose()


def test_restart_reuses_replay_cache_from_disposed_runtime(monkeypatch) -> None:
    context = _prepare_live_start(monkeypatch)

    assert "started" in context.rpc_server.start_rpc_server().lower()
    first_runtime = context.built["runtime"]
    replay_cache = first_runtime.request_replay_cache
    assert context.rpc_server.stop_rpc_server() == "RPC Server stopped."
    assert context.rpc_server._addon_runtime is first_runtime
    assert first_runtime.disposed is True
    monkeypatch.setattr(
        context.rpc_server,
        "RequestReplayCache",
        lambda: pytest.fail("restart must reuse the replay journal"),
    )

    assert "started" in context.rpc_server.start_rpc_server().lower()
    second_runtime = context.built["runtime"]
    assert second_runtime is not first_runtime
    assert second_runtime.request_replay_cache is replay_cache
    second_runtime.dispose()


def test_full_stop_restart_preserves_native_collaboration_contexts(
    monkeypatch,
) -> None:
    context = _prepare_live_start(monkeypatch)
    native_document = SimpleNamespace(
        Name="NativeSession",
        Label="Native document",
        lifecycle_epoch=23,
        persisted_revision=17,
        recovery_state={"status": "Recoverable", "artifact": "native-recovery"},
        revision_stream=(
            {"kind": "DocumentStructure", "revision": 41},
            {"kind": "ObjectState", "subject": "Body", "revision": 73},
        ),
    )
    personal_contexts = {
        (native_document.Name, "actor-native"): {
            "camera": "native-camera",
            "selection": ("Body",),
        }
    }
    personal_context_writes: list[tuple[object, ...]] = []

    def get_document(name):
        return native_document if name == native_document.Name else None

    monkeypatch.setattr(context.rpc_server.FreeCAD, "getDocument", get_document)
    monkeypatch.setattr(
        context.rpc_server.FreeCADGui,
        "getPersonalViewContext",
        lambda document, actor: personal_contexts.get((document, actor)),
        raising=False,
    )
    monkeypatch.setattr(
        context.rpc_server.FreeCADGui,
        "storePersonalViewContext",
        lambda *args: personal_context_writes.append(("store", *args)),
        raising=False,
    )
    monkeypatch.setattr(
        context.rpc_server.FreeCADGui,
        "removePersonalViewContext",
        lambda *args: personal_context_writes.append(("remove", *args)),
        raising=False,
    )
    expected_document_state = {
        "lifecycle_epoch": native_document.lifecycle_epoch,
        "persisted_revision": native_document.persisted_revision,
        "recovery_state": dict(native_document.recovery_state),
        "revision_stream": native_document.revision_stream,
    }
    expected_personal_contexts = {
        key: dict(value) for key, value in personal_contexts.items()
    }

    assert "started" in context.rpc_server.start_rpc_server().lower()
    first_runtime = context.built["runtime"]
    first_bridge = first_runtime.collaboration_bridge
    first_collaboration = first_bridge._collaboration_collaborators
    first_lifecycle = first_bridge._lifecycle_collaborators
    first_gui = first_bridge._gui_collaborators
    first_lookup = first_collaboration.compatibility_api._document_lookup
    assert first_lifecycle.freecad is context.rpc_server.FreeCAD
    assert first_lookup(native_document.Name) is native_document
    assert first_gui.snapshot_personal_view_context(
        native_document.Name, "actor-native"
    ) == personal_contexts[(native_document.Name, "actor-native")]

    assert context.rpc_server.stop_rpc_server() == "RPC Server stopped."
    assert {
        "lifecycle_epoch": native_document.lifecycle_epoch,
        "persisted_revision": native_document.persisted_revision,
        "recovery_state": native_document.recovery_state,
        "revision_stream": native_document.revision_stream,
    } == expected_document_state
    assert personal_contexts == expected_personal_contexts
    assert personal_context_writes == []

    assert "started" in context.rpc_server.start_rpc_server().lower()
    second_runtime = context.built["runtime"]
    second_bridge = second_runtime.collaboration_bridge
    second_collaboration = second_bridge._collaboration_collaborators
    second_lifecycle = second_bridge._lifecycle_collaborators
    second_gui = second_bridge._gui_collaborators
    second_lookup = second_collaboration.compatibility_api._document_lookup
    assert second_runtime is not first_runtime
    assert second_collaboration is not first_collaboration
    assert second_lifecycle is not first_lifecycle
    assert second_gui is not first_gui
    assert second_lifecycle.freecad is context.rpc_server.FreeCAD
    assert second_lookup(native_document.Name) is native_document
    assert second_gui.snapshot_personal_view_context(
        native_document.Name, "actor-native"
    ) == expected_personal_contexts[(native_document.Name, "actor-native")]
    assert {
        "lifecycle_epoch": native_document.lifecycle_epoch,
        "persisted_revision": native_document.persisted_revision,
        "recovery_state": native_document.recovery_state,
        "revision_stream": native_document.revision_stream,
    } == expected_document_state
    assert personal_contexts == expected_personal_contexts
    assert personal_context_writes == []
    assert context.rpc_server.stop_rpc_server() == "RPC Server stopped."
    assert personal_contexts == expected_personal_contexts
    assert personal_context_writes == []


def test_failed_restart_preserves_tombstone_replay_cache(monkeypatch) -> None:
    context = _prepare_live_start(monkeypatch)

    assert "started" in context.rpc_server.start_rpc_server().lower()
    first_runtime = context.built["runtime"]
    replay_cache = first_runtime.request_replay_cache
    assert context.rpc_server.stop_rpc_server() == "RPC Server stopped."
    real_listener_factory = context.rpc_server.FilteredXMLRPCServer
    monkeypatch.setattr(
        context.rpc_server,
        "FilteredXMLRPCServer",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("restart bind failed")
        ),
    )

    failed = context.rpc_server.start_rpc_server()

    assert "could not construct its runtime" in failed.lower()
    assert context.rpc_server._addon_runtime is first_runtime
    assert first_runtime.request_replay_cache is replay_cache
    monkeypatch.setattr(
        context.rpc_server,
        "FilteredXMLRPCServer",
        real_listener_factory,
    )
    monkeypatch.setattr(
        context.rpc_server,
        "RequestReplayCache",
        lambda: pytest.fail("retry must preserve the replay journal"),
    )
    assert "started" in context.rpc_server.start_rpc_server().lower()
    assert context.built["runtime"].request_replay_cache is replay_cache
    context.built["runtime"].dispose()


def test_worker_start_failure_disposes_unpublished_runtime(monkeypatch) -> None:
    context = _prepare_live_start(monkeypatch)

    def fail_start():
        raise RuntimeError("worker start failed")

    context.worker_manager._start = fail_start

    result = context.rpc_server.start_rpc_server()

    assert "could not start its listener" in result.lower()
    assert context.counts["builder"] == 1
    assert context.counts["thread"] == 0
    assert context.rpc_server._addon_runtime is None
    assert context.rpc_server.rpc_server_instance is None
    assert context.listener.cleanup_calls == 1
    assert context.worker_manager.cleanup_calls == 1
    assert context.dispatcher.cleanup_calls == 1


def test_launch_cleanup_failure_retains_exact_runtime_and_blocks_restart(
    monkeypatch,
) -> None:
    context = _prepare_live_start(monkeypatch)
    start_failure = RuntimeError("worker start failed")
    cleanup_failure = RuntimeError("listener close failed")

    def fail_start():
        raise start_failure

    def fail_close():
        context.listener.cleanup_calls += 1
        context.timeline.append("cleanup:listener")
        raise cleanup_failure

    context.worker_manager._start = fail_start
    context.listener.server_close = fail_close

    result = context.rpc_server.start_rpc_server()
    claim = context.rpc_server._runtime_shutdown_claim

    assert "could not start its listener" in result.lower()
    assert claim is not None
    assert claim.runtime is context.built["runtime"]
    assert claim.runtime.listener is context.listener
    assert claim.completed.is_set()
    assert cleanup_failure in claim.failure.exceptions[1].exceptions
    assert (
        context.rpc_server.start_rpc_server()
        == "RPC Server shutdown is still in progress."
    )


def test_construction_cleanup_failure_retains_exact_resource_and_blocks_restart(
    monkeypatch,
) -> None:
    primary = RuntimeError("capability bridge construction failed")
    cleanup_failure = RuntimeError("worker stop failed")
    context = _prepare_live_start(monkeypatch, bridge_failure=primary)

    def fail_stop(timeout=4.0):
        assert timeout == 4.0
        context.worker_manager.cleanup_calls += 1
        context.timeline.append("cleanup:worker_manager")
        raise cleanup_failure

    context.worker_manager.stop = fail_stop

    result = context.rpc_server.start_rpc_server()
    claim = context.rpc_server._runtime_shutdown_claim

    assert "could not construct its runtime" in result.lower()
    assert claim is not None
    assert claim.completed.is_set()
    assert claim.runtime.resources[0][0] is context.worker_manager
    assert cleanup_failure in claim.failure.exceptions
    assert (
        context.rpc_server.start_rpc_server()
        == "RPC Server shutdown is still in progress."
    )


def test_fatal_construction_cleanup_failure_retains_resource_before_propagating(
    monkeypatch,
) -> None:
    primary = _ConstructionFailure("fatal bridge construction")
    cleanup_failure = _CleanupFailure("fatal worker stop")
    context = _prepare_live_start(monkeypatch, bridge_failure=primary)

    def fail_stop(timeout=4.0):
        assert timeout == 4.0
        context.worker_manager.cleanup_calls += 1
        context.timeline.append("cleanup:worker_manager")
        raise cleanup_failure

    context.worker_manager.stop = fail_stop

    with pytest.raises(BaseExceptionGroup) as captured:
        context.rpc_server.start_rpc_server()

    claim = context.rpc_server._runtime_shutdown_claim
    assert captured.value is claim.failure
    assert claim.runtime.resources[0][0] is context.worker_manager
    assert claim.completed.is_set()
    assert (
        context.rpc_server.start_rpc_server()
        == "RPC Server shutdown is still in progress."
    )


def test_authenticated_start_publishes_authentication_only_after_composition(
    monkeypatch,
) -> None:
    context = _prepare_live_start(monkeypatch, authentication_enabled=True)

    result = context.rpc_server.start_rpc_server()

    assert result == "RPC Server started at 127.0.0.1:19875."
    assert context.rpc_server.rpc_session_manager is context.session_manager
    assert context.rpc_server.rpc_runtime_manifest is context.runtime_manifest
    assert context.built["runtime"].session_manager is context.session_manager
    assert (
        context.bridge._collaboration_collaborators.runtime_manifest
        is context.runtime_manifest
    )
    assert (
        context.bridge._execution_collaborators.session_manager
        is context.session_manager
    )
    assert (
        context.bridge._execution_collaborators.runtime_manifest
        is context.runtime_manifest
    )
    assert context.bridge._execution_collaborators.actual_endpoint == {
        "host": "127.0.0.1",
        "port": 19875,
    }
    assert (
        context.rpc_server.rpc_server_actual_endpoint
        is context.bridge._execution_collaborators.actual_endpoint
    )
    assert (
        context.rpc_server.rpc_server_started_at
        == context.bridge._execution_collaborators.server_started_at
    )
    assert context.timeline.index("construct:session_manager") < context.timeline.index(
        "builder:return"
    )
    context.built["runtime"].dispose()


def test_authenticated_restart_rebinds_transport_authentication(
    monkeypatch,
) -> None:
    context = _prepare_live_start(monkeypatch, authentication_enabled=True)

    assert "started" in context.rpc_server.start_rpc_server().lower()
    first_runtime = context.built["runtime"]
    assert context.rpc_server.stop_rpc_server() == "RPC Server stopped."
    assert first_runtime.disposed is True

    assert "started" in context.rpc_server.start_rpc_server().lower()
    second_runtime = context.built["runtime"]
    assert second_runtime is not first_runtime
    assert second_runtime.session_manager is context.session_manager
    assert second_runtime.runtime_manifest is context.runtime_manifest
    assert context.rpc_server.stop_rpc_server() == "RPC Server stopped."


def test_listener_thread_target_retains_composed_listener_identity(monkeypatch) -> None:
    context = _prepare_live_start(monkeypatch)
    context.rpc_server.start_rpc_server()
    launched_thread = context.rpc_server.rpc_server_thread

    context.rpc_server.rpc_server_instance = None
    launched_thread.target()

    assert context.listener.registered == [context.bridge]
    assert context.timeline.count("register:bridge") == 1
    assert context.timeline[-1] == "serve:listener"
    context.built["runtime"].dispose()


def test_runtime_start_does_not_publish_or_launch_partial_failed_graph(
    monkeypatch,
) -> None:
    primary = RuntimeError("capability bridge construction failed")
    context = _prepare_live_start(monkeypatch, bridge_failure=primary)

    result = context.rpc_server.start_rpc_server()

    assert "could not" in result.lower() or "refused" in result.lower()
    assert context.counts == {
        "builder": 1,
        "dispatcher": 1,
        "worker_manager": 1,
        "listener": 0,
        "bridge": 1,
        "thread": 0,
    }
    assert context.rpc_server._addon_runtime is None
    assert context.rpc_server.rpc_server_instance is None
    assert context.rpc_server.gui_dispatcher is None
    assert context.rpc_server.worker_manager is None
    assert context.listener.registered == []
    assert context.dispatcher.cleanup_calls == 1
    assert context.worker_manager.cleanup_calls == 1
    assert context.listener.cleanup_calls == 0
    assert context.timeline[-3:] == [
        "shutdown",
        "cleanup:worker_manager",
        "cleanup:dispatcher",
    ]
    assert "thread:constructed" not in context.timeline


def test_runtime_start_failure_cleans_unpublished_graph_exactly_once(
    monkeypatch,
) -> None:
    context = _prepare_live_start(
        monkeypatch,
        thread_start_failure=RuntimeError("thread start failed"),
    )

    result = context.rpc_server.start_rpc_server()

    assert "could not start its listener" in result.lower()
    assert context.rpc_server._addon_runtime is None
    assert context.rpc_server.rpc_server_instance is None
    assert context.rpc_server.rpc_server_thread is None
    assert context.rpc_server.gui_dispatcher is None
    assert context.rpc_server.worker_manager is None
    assert context.rpc_server.rpc_session_manager is None
    assert context.listener.cleanup_calls == 1
    assert context.worker_manager.cleanup_calls == 1
    assert context.dispatcher.cleanup_calls == 1
    assert context.timeline[-4:] == [
        "shutdown",
        "cleanup:listener",
        "cleanup:worker_manager",
        "cleanup:dispatcher",
    ]


def test_malformed_listener_endpoint_rolls_back_complete_graph(monkeypatch) -> None:
    context = _prepare_live_start(monkeypatch, listener_address=None)

    result = context.rpc_server.start_rpc_server()

    assert "could not construct its runtime" in result.lower()
    assert context.counts["thread"] == 0
    assert context.worker_manager.start_calls == 0
    assert context.rpc_server._addon_runtime is None
    assert context.rpc_server.rpc_server_instance is None
    assert context.listener.cleanup_calls == 1
    assert context.worker_manager.cleanup_calls == 1
    assert context.dispatcher.cleanup_calls == 1
    assert context.timeline[-4:] == [
        "shutdown",
        "cleanup:listener",
        "cleanup:worker_manager",
        "cleanup:dispatcher",
    ]


def test_fatal_thread_start_failure_rolls_back_then_propagates(monkeypatch) -> None:
    primary = _LaunchFailure("fatal thread start")
    context = _prepare_live_start(monkeypatch, thread_start_failure=primary)

    with pytest.raises(_LaunchFailure) as captured:
        context.rpc_server.start_rpc_server()

    assert captured.value is primary
    assert context.rpc_server._addon_runtime is None
    assert context.rpc_server.rpc_server_instance is None
    assert context.rpc_server.rpc_server_thread is None
    assert context.rpc_server.gui_dispatcher is None
    assert context.rpc_server.worker_manager is None
    assert context.listener.cleanup_calls == 1
    assert context.worker_manager.cleanup_calls == 1
    assert context.dispatcher.cleanup_calls == 1
    assert context.timeline[-4:] == [
        "shutdown",
        "cleanup:listener",
        "cleanup:worker_manager",
        "cleanup:dispatcher",
    ]


def test_fatal_auth_manifest_publication_rolls_back_then_propagates(
    monkeypatch,
) -> None:
    primary = _LaunchFailure("fatal authentication manifest publication")
    context = _prepare_live_start(
        monkeypatch,
        authentication_enabled=True,
        manifest_binding_failure=primary,
    )

    with pytest.raises(_LaunchFailure) as captured:
        context.rpc_server.start_rpc_server()

    assert captured.value is primary
    assert context.counts["thread"] == 0
    assert context.rpc_server._addon_runtime is None
    assert context.rpc_server.rpc_server_instance is None
    assert context.rpc_server.rpc_session_manager is None
    assert context.rpc_server.rpc_runtime_manifest is None
    assert context.listener.cleanup_calls == 1
    assert context.worker_manager.cleanup_calls == 1
    assert context.dispatcher.cleanup_calls == 1
    assert context.timeline[-4:] == [
        "shutdown",
        "cleanup:listener",
        "cleanup:worker_manager",
        "cleanup:dispatcher",
    ]
