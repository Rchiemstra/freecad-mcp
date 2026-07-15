"""Unit tests for event-driven, per-request GUI dispatch."""

from __future__ import annotations

import threading
import time

import FreeCADGui
from PySide import QtCore


if not hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand = lambda *_args, **_kwargs: None

from addon.FreeCADMCP.rpc_server.gui_dispatcher import (
    GuiDispatcher,
    GuiTaskError,
)


def _app():
    return QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])


def test_gui_thread_self_dispatch_executes_directly_without_deadlock():
    _app()
    dispatcher = GuiDispatcher()
    assert dispatcher.submit(lambda: 42, timeout=0.01) == 42


def test_self_dispatch_and_queued_dispatch_share_exception_semantics():
    app = _app()
    dispatcher = GuiDispatcher()

    def fail():
        raise ValueError("same failure")

    try:
        dispatcher.submit(fail, timeout=0.01)
    except GuiTaskError as exc:
        direct_error = str(exc)
    else:  # pragma: no cover - assertion aid
        raise AssertionError("direct dispatch did not raise")

    queued_error = []

    def worker():
        try:
            dispatcher.submit(fail, timeout=1.0)
        except GuiTaskError as exc:
            queued_error.append(str(exc))

    thread = threading.Thread(target=worker)
    thread.start()
    deadline = time.monotonic() + 1.0
    while thread.is_alive() and time.monotonic() < deadline:
        app.processEvents()
    thread.join(timeout=0.2)

    assert queued_error == [direct_error]


def test_timed_out_request_cannot_contaminate_the_next_request():
    app = _app()
    dispatcher = GuiDispatcher()
    outcomes = []

    def first():
        try:
            dispatcher.submit(lambda: "late", timeout=0.01)
        except Exception as exc:
            outcomes.append(type(exc).__name__)

    first_thread = threading.Thread(target=first)
    first_thread.start()
    first_thread.join(timeout=0.2)
    assert outcomes == ["GuiDispatchTimeout"]

    second_result = []
    second_thread = threading.Thread(
        target=lambda: second_result.append(dispatcher.submit(lambda: "second", 1.0))
    )
    second_thread.start()
    deadline = time.monotonic() + 1.0
    while second_thread.is_alive() and time.monotonic() < deadline:
        app.processEvents()
    second_thread.join(timeout=0.2)

    assert second_result == ["second"]
    assert dispatcher.pending_count == 0


def _process_until(app, predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.001)
    assert predicate()


def test_burst_is_fifo_has_no_duplicate_execution_and_one_unit_per_callback():
    _app()
    dispatcher = GuiDispatcher()
    executed = []
    results = []
    threads = []
    for value in range(3):
        thread = threading.Thread(
            target=lambda item=value: results.append(
                dispatcher.submit(lambda: executed.append(item) or item, 1.0)
            )
        )
        thread.start()
        threads.append(thread)
        deadline = time.monotonic() + 1.0
        while dispatcher.pending_count < value + 1 and time.monotonic() < deadline:
            time.sleep(0.001)

    dispatcher._drain_one()
    assert executed == [0]
    assert dispatcher.pending_count == 2
    dispatcher._drain_one()
    assert executed == [0, 1]
    assert dispatcher.pending_count == 1
    dispatcher._drain_one()
    for thread in threads:
        thread.join(timeout=0.2)
    assert executed == [0, 1, 2]
    assert sorted(results) == [0, 1, 2]


def test_submission_during_callback_cannot_lose_wakeup():
    app = _app()
    dispatcher = GuiDispatcher()
    first_started = threading.Event()
    release_first = threading.Event()
    results = []

    def first_task():
        first_started.set()
        release_first.wait(1.0)
        return "first"

    first = threading.Thread(
        target=lambda: results.append(
            dispatcher.submit(first_task, 2.0)
        )
    )
    first.start()
    deadline = time.monotonic() + 1.0
    while dispatcher.pending_count != 1 and time.monotonic() < deadline:
        time.sleep(0.001)

    submit_second = threading.Thread(
        target=lambda: (
            first_started.wait(1.0),
            results.append(dispatcher.submit(lambda: "second", 2.0)),
        )
    )
    submit_second.start()
    threading.Timer(0.05, release_first.set).start()
    _process_until(app, lambda: not first.is_alive() and not submit_second.is_alive())
    first.join(timeout=0.2)
    submit_second.join(timeout=0.2)
    assert results == ["first", "second"]


def test_queued_callable_runs_on_dispatcher_thread():
    app = _app()
    dispatcher = GuiDispatcher()
    identity = []
    thread = threading.Thread(
        target=lambda: dispatcher.submit(
            lambda: identity.append(
                QtCore.QThread.currentThread() == dispatcher.thread()
            ),
            1.0,
        )
    )
    thread.start()
    _process_until(app, lambda: not thread.is_alive())
    thread.join(timeout=0.2)
    assert identity == [True]


def test_timeout_before_start_is_skipped_when_callback_arrives_later():
    app = _app()
    dispatcher = GuiDispatcher()
    executed = []
    errors = []
    thread = threading.Thread(
        target=lambda: _capture_error(
            errors,
            lambda: dispatcher.submit(lambda: executed.append(True), 0.01),
        )
    )
    thread.start()
    thread.join(timeout=0.2)
    app.processEvents()
    assert errors == ["GuiDispatchTimeout"]
    assert executed == []


def _capture_error(errors, callable_):
    try:
        callable_()
    except Exception as exc:
        errors.append(type(exc).__name__)


def test_timeout_after_start_keeps_late_result_on_original_request():
    app = _app()
    dispatcher = GuiDispatcher()
    release = threading.Event()
    errors = []
    late_executed = []

    def late_task():
        release.wait(1.0)
        late_executed.append("late")
        return "late"

    first = threading.Thread(
        target=lambda: _capture_error(
            errors,
            lambda: dispatcher.submit(late_task, 0.02),
        )
    )
    first.start()
    deadline = time.monotonic() + 1.0
    while dispatcher.pending_count != 1 and time.monotonic() < deadline:
        time.sleep(0.001)
    threading.Timer(0.08, release.set).start()
    dispatcher._drain_one()
    first.join(timeout=0.2)
    assert errors == ["GuiDispatchTimeout"]

    second = []
    thread = threading.Thread(
        target=lambda: second.append(dispatcher.submit(lambda: "second", 1.0))
    )
    thread.start()
    _process_until(app, lambda: not thread.is_alive())
    thread.join(timeout=0.2)
    assert late_executed == ["late"]
    assert second == ["second"]
