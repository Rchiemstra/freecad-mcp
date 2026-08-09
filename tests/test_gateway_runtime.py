from __future__ import annotations

import asyncio
import builtins
import importlib
import importlib.util
import inspect
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATH = ROOT / "addon" / "FreeCADMCP" / "runtime.py"

_COMPONENT_FIELDS = (
    "listener",
    "dispatcher",
    "worker_manager",
    "session_manager",
    "request_replay_cache",
    "inflight_requests",
    "collaboration_bridge",
)
_CONSTRUCTOR_FIELDS = (
    *_COMPONENT_FIELDS,
    "shutdown_requested",
    "owned_resources",
)


def _runtime_module() -> ModuleType:
    return importlib.import_module("addon.FreeCADMCP.runtime")


def _dependencies() -> dict[str, object]:
    return {name: object() for name in _COMPONENT_FIELDS}


def _runtime(
    *,
    dependencies: dict[str, object | None] | None = None,
    shutdown_requested: threading.Event | None = None,
    owned_resources: object = (),
) -> Any:
    addon_runtime = _runtime_module().AddonRuntime
    return addon_runtime(
        **(dependencies if dependencies is not None else _dependencies()),
        shutdown_requested=(
            shutdown_requested
            if shutdown_requested is not None
            else threading.Event()
        ),
        owned_resources=owned_resources,
    )


def test_runtime_import_succeeds_with_freecad_and_qt_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocked_roots = {
        "FreeCAD",
        "FreeCADGui",
        "PySide",
        "PySide2",
        "PySide6",
        "Qt",
    }
    real_import = builtins.__import__

    def rejecting_import(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name.partition(".")[0] in blocked_roots:
            raise AssertionError(f"blocked dependency imported: {name}")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", rejecting_import)
    with pytest.raises(AssertionError, match="blocked dependency imported"):
        builtins.__import__("FreeCAD")

    isolated_name = "_phase8_isolated_gateway_runtime"
    spec = importlib.util.spec_from_file_location(isolated_name, RUNTIME_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[isolated_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(isolated_name, None)

    assert module.__all__ == ["AddonRuntime"]
    assert module.AddonRuntime.__module__ == isolated_name


def test_constructor_has_only_the_frozen_keyword_interface() -> None:
    addon_runtime = _runtime_module().AddonRuntime
    parameters = inspect.signature(addon_runtime).parameters

    assert tuple(parameters) == _CONSTRUCTOR_FIELDS
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in parameters.values()
    )
    with pytest.raises(TypeError):
        addon_runtime(*[object() for _ in _CONSTRUCTOR_FIELDS])


def test_construction_preserves_exact_dependency_and_ownership_identities() -> None:
    dependencies = _dependencies()
    shutdown_requested = threading.Event()
    disposed: list[str] = []

    def disposer() -> None:
        disposed.append("listener")

    owned_resources = iter(((dependencies["listener"], disposer),))

    runtime = _runtime(
        dependencies=dependencies,
        shutdown_requested=shutdown_requested,
        owned_resources=owned_resources,
    )

    for name, dependency in dependencies.items():
        assert getattr(runtime, name) is dependency
    assert runtime.shutdown_requested is shutdown_requested
    assert disposed == []
    runtime.dispose()
    assert disposed == ["listener"]


def test_all_component_resources_are_optional() -> None:
    runtime = _runtime_module().AddonRuntime()

    assert all(getattr(runtime, name) is None for name in _COMPONENT_FIELDS)
    assert not runtime.shutdown_requested.is_set()
    assert runtime.dispose() is None


class _PassiveDependency:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def _called(self, name: str) -> None:
        self.calls.append(name)

    def start(self) -> None:
        self._called("start")

    def bind(self) -> None:
        self._called("bind")

    def connect(self) -> None:
        self._called("connect")

    def listen(self) -> None:
        self._called("listen")

    def serve(self) -> None:
        self._called("serve")

    def serve_forever(self) -> None:
        self._called("serve_forever")

    def dispose(self) -> None:
        self._called("dispose")


def test_construction_does_not_start_or_dispose_any_component() -> None:
    dependencies = {name: _PassiveDependency() for name in _COMPONENT_FIELDS}
    listener = dependencies["listener"]

    _runtime(
        dependencies=dependencies,
        owned_resources=((listener, listener.dispose),),
    )

    assert all(not dependency.calls for dependency in dependencies.values())


def test_runtime_is_frozen_and_slotted() -> None:
    runtime = _runtime()

    assert not hasattr(runtime, "__dict__")
    with pytest.raises(FrozenInstanceError):
        runtime.listener = object()
    with pytest.raises((AttributeError, FrozenInstanceError, TypeError)):
        runtime.another_resource = object()


@pytest.mark.parametrize(
    ("resource_factory", "disposer_factory", "match"),
    [
        (lambda dependencies: None, lambda: lambda: None, "None"),
        (lambda dependencies: object(), lambda: lambda: None, "owned|component"),
        (lambda dependencies: dependencies["listener"], object, "callable|disposer"),
    ],
)
def test_owned_resources_reject_invalid_entries(
    resource_factory: Any,
    disposer_factory: Any,
    match: str,
) -> None:
    dependencies = _dependencies()

    with pytest.raises((TypeError, ValueError), match=match):
        _runtime(
            dependencies=dependencies,
            owned_resources=((resource_factory(dependencies), disposer_factory()),),
        )


def test_owned_resource_membership_uses_identity_not_equality() -> None:
    class EqualToEverything:
        def __eq__(self, other: object) -> bool:
            return True

    dependencies = _dependencies()
    dependencies["listener"] = EqualToEverything()

    with pytest.raises((TypeError, ValueError), match=r"owned|component"):
        _runtime(
            dependencies=dependencies,
            owned_resources=((EqualToEverything(), lambda: None),),
        )


def test_owned_resources_reject_duplicate_resource_identity() -> None:
    dependencies = _dependencies()
    listener = dependencies["listener"]

    with pytest.raises((TypeError, ValueError), match=r"duplicate|once"):
        _runtime(
            dependencies=dependencies,
            owned_resources=(
                (listener, lambda: None),
                (listener, lambda: None),
            ),
        )


def test_disposal_sets_shutdown_before_callbacks_and_uses_reverse_order() -> None:
    dependencies = _dependencies()
    shutdown_requested = threading.Event()
    calls: list[str] = []
    owned_resources = tuple(
        (
            dependencies[name],
            lambda name=name: (
                calls.append(name)
                if shutdown_requested.is_set()
                else pytest.fail("shutdown event was not set before disposal")
            ),
        )
        for name in ("listener", "dispatcher", "worker_manager")
    )
    runtime = _runtime(
        dependencies=dependencies,
        shutdown_requested=shutdown_requested,
        owned_resources=owned_resources,
    )

    result = runtime.dispose()

    assert result is None
    assert shutdown_requested.is_set()
    assert calls == ["worker_manager", "dispatcher", "listener"]


def test_double_disposal_is_an_exact_once_noop() -> None:
    dependencies = _dependencies()
    calls: list[str] = []
    runtime = _runtime(
        dependencies=dependencies,
        owned_resources=(
            (dependencies["listener"], lambda: calls.append("listener")),
        ),
    )

    assert runtime.disposed is False
    assert runtime.dispose() is None
    assert runtime.disposed is True
    assert runtime.dispose() is None
    assert calls == ["listener"]


def test_concurrent_disposal_runs_every_callback_exactly_once() -> None:
    dependencies = _dependencies()
    callback_entered = threading.Event()
    release_callback = threading.Event()
    calls: list[str] = []

    def dispose_listener() -> None:
        calls.append("listener")

    def dispose_dispatcher() -> None:
        calls.append("dispatcher")
        callback_entered.set()
        assert release_callback.wait(timeout=5)

    runtime = _runtime(
        dependencies=dependencies,
        owned_resources=(
            (dependencies["listener"], dispose_listener),
            (dependencies["dispatcher"], dispose_dispatcher),
        ),
    )
    callers = 12
    starting = threading.Barrier(callers + 1)

    def invoke_dispose() -> None:
        starting.wait(timeout=5)
        assert runtime.dispose() is None

    with ThreadPoolExecutor(max_workers=callers) as executor:
        futures = [executor.submit(invoke_dispose) for _ in range(callers)]
        starting.wait(timeout=5)
        assert callback_entered.wait(timeout=5)
        assert not any(future.done() for future in futures)
        release_callback.set()
        for future in futures:
            future.result(timeout=5)

    assert calls == ["dispatcher", "listener"]
    assert runtime.dispose() is None
    assert calls == ["dispatcher", "listener"]


def test_disposer_reentry_on_owner_thread_is_an_exact_once_noop() -> None:
    dependencies = _dependencies()
    calls: list[str] = []
    runtime = None

    def dispose_listener() -> None:
        calls.append("listener_enter")
        assert runtime is not None
        assert runtime.dispose() is None
        calls.append("listener_exit")

    runtime = _runtime(
        dependencies=dependencies,
        owned_resources=((dependencies["listener"], dispose_listener),),
    )

    assert runtime.dispose() is None
    assert calls == ["listener_enter", "listener_exit"]
    assert runtime.dispose() is None


def test_disposal_aggregates_ordered_failures_after_all_callbacks() -> None:
    dependencies = _dependencies()
    calls: list[str] = []
    listener_failure = RuntimeError("listener failed")
    worker_failure = LookupError("worker failed")

    def fail_listener() -> None:
        calls.append("listener")
        raise listener_failure

    def dispose_dispatcher() -> None:
        calls.append("dispatcher")

    def fail_worker() -> None:
        calls.append("worker_manager")
        raise worker_failure

    runtime = _runtime(
        dependencies=dependencies,
        owned_resources=(
            (dependencies["listener"], fail_listener),
            (dependencies["dispatcher"], dispose_dispatcher),
            (dependencies["worker_manager"], fail_worker),
        ),
    )

    with pytest.raises(ExceptionGroup) as captured:
        runtime.dispose()

    assert captured.value.message == "AddonRuntime disposal failed"
    assert captured.value.exceptions == (worker_failure, listener_failure)
    assert calls == ["worker_manager", "dispatcher", "listener"]
    with pytest.raises(ExceptionGroup) as repeated:
        runtime.dispose()
    assert repeated.value.message == "AddonRuntime disposal failed"
    assert repeated.value.exceptions == (worker_failure, listener_failure)
    assert calls == ["worker_manager", "dispatcher", "listener"]


def test_disposal_aggregates_fatal_cancellation_and_finishes_cleanup() -> None:
    dependencies = _dependencies()
    calls: list[str] = []
    cancelled = asyncio.CancelledError("cancelled during shutdown")

    def dispose_listener() -> None:
        calls.append("listener")

    def cancel_dispatcher() -> None:
        calls.append("dispatcher")
        raise cancelled

    runtime = _runtime(
        dependencies=dependencies,
        owned_resources=(
            (dependencies["listener"], dispose_listener),
            (dependencies["dispatcher"], cancel_dispatcher),
        ),
    )

    with pytest.raises(BaseExceptionGroup) as captured:
        runtime.dispose()

    assert captured.value.message == "AddonRuntime disposal failed"
    assert captured.value.exceptions == (cancelled,)
    assert calls == ["dispatcher", "listener"]
    with pytest.raises(BaseExceptionGroup):
        runtime.dispose()


def test_shutdown_signal_failure_does_not_skip_owned_cleanup() -> None:
    class FailingShutdownSignal:
        def set(self) -> None:
            raise RuntimeError("shutdown signal failed")

    dependencies = _dependencies()
    calls: list[str] = []
    runtime = _runtime_module().AddonRuntime(
        **dependencies,
        shutdown_requested=FailingShutdownSignal(),
        owned_resources=(
            (dependencies["listener"], lambda: calls.append("listener")),
        ),
    )

    with pytest.raises(ExceptionGroup) as captured:
        runtime.dispose()

    assert [str(error) for error in captured.value.exceptions] == [
        "shutdown signal failed"
    ]
    assert calls == ["listener"]
