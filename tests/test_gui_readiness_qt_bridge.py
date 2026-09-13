"""Real-Qt concurrency contracts for the mutation-readiness bridge."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from typing import Any

import FreeCAD
import pytest
from PySide import QtCore

if not hasattr(QtCore, "QCoreApplication"):
    pytest.skip(
        "real PySide QCoreApplication is unavailable",
        allow_module_level=True,
    )

from addon.FreeCADMCP.dispatch.gui_request import GuiDeferDecision
from addon.FreeCADMCP import runtime as runtime_module
from addon.FreeCADMCP.rpc_server.gui_dispatcher_qt import GuiDispatcher
from addon.FreeCADMCP.rpc_server import server_shutdown

pytestmark = pytest.mark.unit


def _app():
    return QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])


def _pump_until(app, predicate, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.001)
    assert predicate()


def _wait_until(predicate, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.001)
    assert predicate()


def _capture(callable_, results: list[Any], errors: list[BaseException]) -> None:
    try:
        results.append(callable_())
    except BaseException as exc:
        errors.append(exc)


def _dispatcher(monkeypatch, *, remove=None):
    observers: list[Any] = []
    removals: list[tuple[Any, int, bool]] = []
    owner_thread = threading.get_ident()

    monkeypatch.setattr(
        FreeCAD,
        "addDocumentObserver",
        observers.append,
        raising=False,
    )

    def remove_observer(observer):
        removals.append(
            (
                observer,
                threading.get_ident(),
                QtCore.QThread.currentThread() == dispatcher.thread(),
            )
        )
        if remove is not None:
            remove(observer)

    monkeypatch.setattr(
        FreeCAD,
        "removeDocumentObserver",
        remove_observer,
        raising=False,
    )
    dispatcher = GuiDispatcher()
    assert len(observers) == 1
    return dispatcher, observers[0], removals, owner_thread


def test_worker_document_events_are_delivered_on_qobject_owner(monkeypatch) -> None:
    app = _app()
    dispatcher, _observer, _removals, owner_thread = _dispatcher(monkeypatch)
    delivered: list[tuple[str, str, int, bool]] = []
    dispatcher._core.notify_document_readiness_changed = lambda name: delivered.append(
        (
            "stable",
            name,
            threading.get_ident(),
            QtCore.QThread.currentThread() == dispatcher.thread(),
        )
    )
    dispatcher._core.notify_document_deleted = lambda name: delivered.append(
        (
            "deleted",
            name,
            threading.get_ident(),
            QtCore.QThread.currentThread() == dispatcher.thread(),
        )
    )

    emitter = threading.Thread(
        target=lambda: (
            dispatcher._queue_stable_document("StableDoc"),
            dispatcher._queue_deleted_document("DeletedDoc"),
        )
    )
    emitter.start()
    emitter.join(timeout=1.0)

    assert delivered == []
    _pump_until(app, lambda: len(delivered) == 2)

    assert {(kind, name) for kind, name, _thread, _owner in delivered} == {
        ("stable", "StableDoc"),
        ("deleted", "DeletedDoc"),
    }
    assert all(thread == owner_thread and owner for _, _, thread, owner in delivered)
    dispatcher.dispose(1.0)


def test_queued_stable_event_closes_probe_defer_race_and_preserves_order(
    monkeypatch,
) -> None:
    app = _app()
    dispatcher, _observer, _removals, _owner_thread = _dispatcher(monkeypatch)
    blocked = {"value": True}
    executions: list[str] = []
    completions: list[str] = []
    results: list[Any] = []
    errors: list[BaseException] = []

    def probe():
        if not blocked["value"]:
            return None
        blocked["value"] = False
        emitter = threading.Thread(
            target=lambda: dispatcher._queue_stable_document("Model")
        )
        emitter.start()
        emitter.join(timeout=1.0)
        return GuiDeferDecision(("Model",), "native_recomputing")

    first = threading.Thread(
        target=_capture,
        args=(
            lambda: dispatcher.submit(
                lambda: executions.append("first") or "first",
                1.0,
                request_id="first-request",
                session_id="session",
                document_keys=("Model",),
                defer_probe=probe,
                on_complete=lambda request_id, _outcome: completions.append(
                    request_id
                ),
            ),
            results,
            errors,
        ),
    )
    second = threading.Thread(
        target=_capture,
        args=(
            lambda: dispatcher.submit(
                lambda: executions.append("second") or "second",
                1.0,
                request_id="second-request",
                session_id="session",
                document_keys=("Model",),
            ),
            results,
            errors,
        ),
    )
    first.start()
    _wait_until(lambda: dispatcher.pending_count == 1)
    second.start()
    _wait_until(lambda: dispatcher.pending_count == 2)

    _pump_until(app, lambda: not first.is_alive() and not second.is_alive())
    first.join(timeout=0.2)
    second.join(timeout=0.2)

    assert errors == []
    assert executions == ["first", "second"]
    assert sorted(results) == ["first", "second"]
    assert completions == ["first-request"]
    assert dispatcher.pending_count == 0
    dispatcher.dispose(1.0)


def test_off_owner_disposal_waits_for_owner_removal(monkeypatch) -> None:
    app = _app()
    dispatcher, observer, removals, owner_thread = _dispatcher(monkeypatch)
    results: list[Any] = []
    errors: list[BaseException] = []
    worker = threading.Thread(
        target=_capture,
        args=(lambda: dispatcher.dispose(1.0), results, errors),
    )
    worker.start()
    _pump_until(app, lambda: not worker.is_alive())
    worker.join(timeout=0.2)

    assert results == [None]
    assert errors == []
    assert removals == [(observer, owner_thread, True)]


def test_off_owner_disposal_failure_retains_and_retries(monkeypatch) -> None:
    app = _app()
    fail = {"value": True}

    def remove(_observer):
        if fail["value"]:
            raise RuntimeError("observer registry busy")

    dispatcher, observer, removals, owner_thread = _dispatcher(
        monkeypatch,
        remove=remove,
    )
    first_errors: list[BaseException] = []
    first = threading.Thread(
        target=_capture,
        args=(lambda: dispatcher.dispose(1.0), [], first_errors),
    )
    first.start()
    _pump_until(app, lambda: not first.is_alive())
    first.join(timeout=0.2)

    assert len(first_errors) == 1
    assert "observer registry busy" in str(first_errors[0])
    assert dispatcher.readiness_observer_cleanup_status["installed"] is True
    assert dispatcher.readiness_observer_cleanup_status["retryable"] is True

    fail["value"] = False
    retry_results: list[Any] = []
    retry_errors: list[BaseException] = []
    retry = threading.Thread(
        target=_capture,
        args=(lambda: dispatcher.dispose(1.0), retry_results, retry_errors),
    )
    retry.start()
    _pump_until(app, lambda: not retry.is_alive())
    retry.join(timeout=0.2)

    assert retry_results == [None]
    assert retry_errors == []
    assert removals == [
        (observer, owner_thread, True),
        (observer, owner_thread, True),
    ]


def test_owner_about_to_quit_shutdown_needs_no_event_pump(monkeypatch) -> None:
    _app()
    dispatcher, observer, removals, owner_thread = _dispatcher(monkeypatch)
    runtime = runtime_module.AddonRuntime(
        dispatcher=dispatcher,
        shutdown_requested=threading.Event(),
        owned_resources=(
            (
                dispatcher,
                lambda: runtime_module._dispose_dispatcher(dispatcher),
            ),
        ),
    )
    dependencies = SimpleNamespace(
        _runtime_lifecycle_lock=threading.RLock(),
        _runtime_shutdown_claim=None,
        _addon_runtime=runtime,
        RPC_SHUTDOWN_CANCELLATION_WAIT_SECONDS=0.1,
    )

    result = server_shutdown.stop_rpc_server(
        dependencies=dependencies,
        wait_for_completion=True,
    )

    assert result == "RPC Server stopped."
    assert removals == [(observer, owner_thread, True)]
    assert runtime.dispatcher is None
    assert dependencies._runtime_shutdown_claim is None


def test_owner_joining_remote_shutdown_prepares_queued_dispatcher(monkeypatch) -> None:
    _app()
    dispatcher, observer, removals, owner_thread = _dispatcher(monkeypatch)
    runtime = runtime_module.AddonRuntime(
        dispatcher=dispatcher,
        shutdown_requested=threading.Event(),
        owned_resources=(
            (
                dispatcher,
                lambda: runtime_module._dispose_dispatcher(dispatcher),
            ),
        ),
    )
    dependencies = SimpleNamespace(
        _runtime_lifecycle_lock=threading.RLock(),
        _runtime_shutdown_claim=None,
        _addon_runtime=runtime,
        RPC_SHUTDOWN_CANCELLATION_WAIT_SECONDS=0.1,
    )
    remote_results: list[Any] = []
    remote_errors: list[BaseException] = []
    remote = threading.Thread(
        target=_capture,
        args=(
            lambda: server_shutdown.stop_rpc_server(
                dependencies=dependencies,
                wait_for_completion=True,
            ),
            remote_results,
            remote_errors,
        ),
    )
    remote.start()
    _wait_until(
        lambda: dependencies._runtime_shutdown_claim is not None
        and dispatcher.readiness_observer_cleanup_status["cleanup_pending"]
    )

    owner_result = server_shutdown.stop_rpc_server(
        dependencies=dependencies,
        wait_for_completion=True,
    )
    remote.join(timeout=1.0)

    assert owner_result == "RPC Server stopped."
    assert remote_results == ["RPC Server stopped."]
    assert remote_errors == []
    assert removals == [(observer, owner_thread, True)]
    assert runtime.dispatcher is None
    assert dependencies._runtime_shutdown_claim is None


def test_late_qobject_deletion_allows_retained_runtime_retry(monkeypatch) -> None:
    app = _app()
    dispatcher, observer, removals, owner_thread = _dispatcher(monkeypatch)
    runtime = runtime_module.AddonRuntime(
        dispatcher=dispatcher,
        shutdown_requested=threading.Event(),
        owned_resources=(
            (dispatcher, lambda: dispatcher.dispose(0.02)),
        ),
    )
    dependencies = SimpleNamespace(
        _runtime_lifecycle_lock=threading.RLock(),
        _runtime_shutdown_claim=None,
        _addon_runtime=runtime,
        RPC_SHUTDOWN_CANCELLATION_WAIT_SECONDS=0.1,
    )
    first_results: list[Any] = []
    first_errors: list[BaseException] = []
    first = threading.Thread(
        target=_capture,
        args=(
            lambda: server_shutdown.stop_rpc_server(
                dependencies=dependencies,
                wait_for_completion=True,
            ),
            first_results,
            first_errors,
        ),
    )
    first.start()
    first.join(timeout=1.0)

    assert first_errors == []
    assert len(first_results) == 1
    assert first_results[0].startswith("RPC Server shutdown failed:")
    assert runtime.dispatcher is dispatcher
    assert runtime.disposal_retryable is True

    _pump_until(app, lambda: len(removals) == 1)
    deferred_delete = getattr(QtCore.QEvent, "DeferredDelete", None)
    if deferred_delete is None:
        deferred_delete = QtCore.QEvent.Type.DeferredDelete
    deadline = time.monotonic() + 1.0
    deleted = False
    while not deleted and time.monotonic() < deadline:
        QtCore.QCoreApplication.sendPostedEvents(None, deferred_delete)
        app.processEvents()
        try:
            dispatcher.thread()
        except RuntimeError:
            deleted = True
    assert deleted is True

    retry = server_shutdown.stop_rpc_server(
        dependencies=dependencies,
        wait_for_completion=True,
    )

    assert retry == "RPC Server stopped."
    assert removals == [(observer, owner_thread, True)]
    assert runtime.dispatcher is None
    assert dependencies._runtime_shutdown_claim is None
