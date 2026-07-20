"""Unit tests for event-driven, per-request GUI dispatch."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import FreeCADGui
from PySide import QtCore


if not hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand = lambda *_args, **_kwargs: None

from addon.FreeCADMCP.rpc_server import gui_dispatcher as gui_dispatcher_module
from addon.FreeCADMCP.rpc_server.gui_dispatcher import (
    GuiBusyAfterTimeout,
    GuiDispatcher,
    GuiTaskError,
)


def _app():
    return QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])


class _FakeQApp:
    """Plain stand-in for QApplication.instance() (not a MagicMock).

    MagicMock apps are ignored by the busy guard so stubbed PySide never
    looks permanently busy; busy-path tests must use a real object.
    """

    def __init__(self, *, mouse=None, popup=None, modal=None):
        no_button = getattr(QtCore.Qt, "NoButton", 0)
        self._mouse = mouse if mouse is not None else no_button
        self._popup = popup
        self._modal = modal

    def mouseButtons(self):
        return self._mouse

    def activePopupWidget(self):
        return self._popup

    def activeModalWidget(self):
        return self._modal


def _fake_qapp(*, mouse=None, popup=None, modal=None):
    return _FakeQApp(mouse=mouse, popup=popup, modal=modal)


def _queue_one(dispatcher, value="task"):
    """Submit one request from a worker thread and wait until it is queued."""
    result = []
    thread = threading.Thread(
        target=lambda: result.append(dispatcher.submit(lambda: value, 2.0))
    )
    thread.start()
    deadline = time.monotonic() + 1.0
    while dispatcher.pending_count < 1 and time.monotonic() < deadline:
        time.sleep(0.001)
    return thread, result


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


def test_running_timeout_rejects_new_work_until_original_request_finishes():
    _app()
    dispatcher = GuiDispatcher()
    started = threading.Event()
    release = threading.Event()
    first_errors = []

    def slow_task():
        started.set()
        release.wait(1.0)
        return "late"

    def submit_first():
        try:
            dispatcher.submit(slow_task, 0.02)
        except Exception as exc:
            first_errors.append(exc)

    first = threading.Thread(target=submit_first)
    first.start()
    deadline = time.monotonic() + 1.0
    while dispatcher.pending_count != 1 and time.monotonic() < deadline:
        time.sleep(0.001)

    drain = threading.Thread(target=dispatcher._drain_one)
    drain.start()
    assert started.wait(0.2)
    first.join(timeout=0.2)

    assert len(first_errors) == 1
    assert "execution continues in FreeCAD" in str(first_errors[0])

    second_errors = []

    def submit_second():
        try:
            dispatcher.submit(lambda: "must not run", 1.0)
        except Exception as exc:
            second_errors.append(exc)

    second = threading.Thread(target=submit_second)
    second.start()
    second.join(timeout=0.2)
    assert len(second_errors) == 1
    assert isinstance(second_errors[0], GuiBusyAfterTimeout)
    assert "new GUI work is rejected" in str(second_errors[0])

    release.set()
    drain.join(timeout=0.2)
    assert dispatcher.submit(lambda: "recovered", 0.01) == "recovered"


def test_drain_defers_while_mouse_button_held(monkeypatch):
    """Regression: GUI work must not run during 3D-view mouse drag."""
    _app()
    dispatcher = GuiDispatcher()
    executed = []
    rescheduled = []

    left = getattr(QtCore.Qt, "LeftButton", 1)
    fake_app = _fake_qapp(mouse=left)
    monkeypatch.setattr(
        gui_dispatcher_module.QtWidgets.QApplication,
        "instance",
        staticmethod(lambda: fake_app),
    )
    monkeypatch.setattr(
        gui_dispatcher_module.QtCore.QTimer,
        "singleShot",
        staticmethod(lambda _ms, slot: rescheduled.append(slot)),
    )

    thread, result = _queue_one(dispatcher, value="should-wait")
    assert dispatcher.pending_count == 1

    dispatcher._drain_one()

    assert executed == []
    assert dispatcher.pending_count == 1
    assert len(rescheduled) == 1
    assert thread.is_alive()

    # Clear the drag and drain again — request must complete.
    fake_app._mouse = getattr(QtCore.Qt, "NoButton", 0)
    dispatcher._drain_one()
    thread.join(timeout=0.5)
    assert result == ["should-wait"]
    assert dispatcher.pending_count == 0


def test_drain_defers_while_popup_or_modal_is_active(monkeypatch):
    _app()
    dispatcher = GuiDispatcher()
    rescheduled = []
    fake_app = _fake_qapp(popup=object())
    monkeypatch.setattr(
        gui_dispatcher_module.QtWidgets.QApplication,
        "instance",
        staticmethod(lambda: fake_app),
    )
    monkeypatch.setattr(
        gui_dispatcher_module.QtCore.QTimer,
        "singleShot",
        staticmethod(lambda _ms, slot: rescheduled.append(slot)),
    )

    thread, result = _queue_one(dispatcher, value="popup-blocked")
    dispatcher._drain_one()
    assert dispatcher.pending_count == 1
    assert rescheduled

    fake_app._popup = None
    fake_app._modal = object()
    rescheduled.clear()
    dispatcher._drain_one()
    assert dispatcher.pending_count == 1
    assert rescheduled

    fake_app._modal = None
    dispatcher._drain_one()
    thread.join(timeout=0.5)
    assert result == ["popup-blocked"]


def test_drain_runs_immediately_when_no_mouse_popup_or_modal(monkeypatch):
    _app()
    dispatcher = GuiDispatcher()
    fake_app = _fake_qapp()
    monkeypatch.setattr(
        gui_dispatcher_module.QtWidgets.QApplication,
        "instance",
        staticmethod(lambda: fake_app),
    )
    single_shot = MagicMock()
    monkeypatch.setattr(
        gui_dispatcher_module.QtCore.QTimer,
        "singleShot",
        single_shot,
    )

    thread, result = _queue_one(dispatcher, value="now")
    dispatcher._drain_one()
    thread.join(timeout=0.5)
    assert result == ["now"]
    single_shot.assert_not_called()


def test_deferred_drag_request_is_not_lost_across_multiple_busy_drains(monkeypatch):
    """Repeated busy drains must keep the same pending request (no drop / dup)."""
    _app()
    dispatcher = GuiDispatcher()
    wakes = []
    left = getattr(QtCore.Qt, "LeftButton", 1)
    fake_app = _fake_qapp(mouse=left)
    monkeypatch.setattr(
        gui_dispatcher_module.QtWidgets.QApplication,
        "instance",
        staticmethod(lambda: fake_app),
    )
    monkeypatch.setattr(
        gui_dispatcher_module.QtCore.QTimer,
        "singleShot",
        staticmethod(lambda _ms, slot: wakes.append(slot)),
    )

    thread, result = _queue_one(dispatcher, value="once")
    for _ in range(5):
        dispatcher._drain_one()
        assert dispatcher.pending_count == 1
    assert len(wakes) == 5

    fake_app._mouse = getattr(QtCore.Qt, "NoButton", 0)
    dispatcher._drain_one()
    thread.join(timeout=0.5)
    assert result == ["once"]
    assert dispatcher.pending_count == 0
