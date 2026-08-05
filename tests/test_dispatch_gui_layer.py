"""Focused contracts for the framework-free GUI dispatch layer."""

from __future__ import annotations

import ast
import inspect
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from addon.FreeCADMCP.dispatch import gui_submit
from addon.FreeCADMCP.dispatch.gui_core import GuiDispatchCore
from addon.FreeCADMCP.dispatch.gui_errors import (
    GuiBusyAfterTimeout,
    GuiDispatchError,
    GuiDispatchTimeout,
    GuiTaskError,
)


class _Harness:
    def __init__(self) -> None:
        self.owner = threading.get_ident()
        self.wakes: list[int] = []
        self.scheduled: list[tuple[int, Any]] = []
        self.events: list[str] = []
        self.busy = False

    def is_gui_thread(self) -> bool:
        return threading.get_ident() == self.owner

    def wake(self) -> None:
        self.wakes.append(threading.get_ident())

    def schedule(self, delay_ms: int, callback) -> None:
        self.scheduled.append((delay_ms, callback))

    def emit(self, _source: str, event: str, **_fields: Any) -> None:
        self.events.append(event)

    def core(self, **overrides: Any) -> GuiDispatchCore:
        return GuiDispatchCore(
            is_gui_thread=overrides.get("is_gui_thread", self.is_gui_thread),
            wake_gui=overrides.get("wake_gui", self.wake),
            schedule_wake=overrides.get("schedule_wake", self.schedule),
            gui_busy=overrides.get("gui_busy", lambda: self.busy),
            emit_telemetry=overrides.get("emit_telemetry", self.emit),
        )


def _wait_until(predicate, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.001)
    assert predicate()


def _capture(target, results: list[Any], errors: list[BaseException]) -> None:
    try:
        results.append(target())
    except BaseException as exc:
        errors.append(exc)


@pytest.mark.unit
def test_off_owner_fifo_runs_exactly_once_on_injected_owner() -> None:
    harness = _Harness()
    core = harness.core()
    execution: list[tuple[int, int]] = []
    results: list[int] = []
    errors: list[BaseException] = []
    threads = []

    for value in range(3):
        thread = threading.Thread(
            target=_capture,
            args=(
                lambda item=value: core.submit(
                    lambda: execution.append((item, threading.get_ident())) or item,
                    1.0,
                ),
                results,
                errors,
            ),
        )
        thread.start()
        threads.append(thread)
        _wait_until(lambda expected=value + 1: core.pending_count == expected)

    assert all(thread.is_alive() for thread in threads)
    for remaining in (2, 1, 0):
        core.drain_one()
        assert core.pending_count == remaining
    for thread in threads:
        thread.join(timeout=1.0)

    assert errors == []
    assert sorted(results) == [0, 1, 2]
    assert execution == [(0, harness.owner), (1, harness.owner), (2, harness.owner)]
    assert harness.events.count("gui_execution_started") == 3
    assert harness.events.count("gui_execution_completed") == 3


@pytest.mark.unit
def test_off_owner_drain_is_rejected_without_executing_or_losing_work() -> None:
    harness = _Harness()
    core = harness.core()
    executed: list[int] = []
    results: list[int] = []
    submit_errors: list[BaseException] = []
    submitter = threading.Thread(
        target=_capture,
        args=(
            lambda: core.submit(
                lambda: executed.append(threading.get_ident()) or 7,
                1.0,
            ),
            results,
            submit_errors,
        ),
    )
    submitter.start()
    _wait_until(lambda: core.pending_count == 1)

    drain_errors: list[BaseException] = []
    off_owner = threading.Thread(
        target=_capture,
        args=(core.drain_one, [], drain_errors),
    )
    off_owner.start()
    off_owner.join(timeout=1.0)

    assert len(drain_errors) == 1
    assert type(drain_errors[0]) is GuiDispatchError
    assert "owner thread" in str(drain_errors[0])
    assert executed == []
    assert core.pending_count == 1

    core.drain_one()
    submitter.join(timeout=1.0)
    assert submit_errors == []
    assert results == [7]
    assert executed == [harness.owner]


@pytest.mark.unit
def test_direct_owner_submit_and_task_error_share_stable_surface() -> None:
    harness = _Harness()
    core = harness.core(emit_telemetry=lambda *_args, **_kwargs: 1 / 0)

    assert core.submit(lambda: 42, 0.01) == 42

    def fail() -> None:
        raise ValueError("same failure")

    with pytest.raises(GuiTaskError) as caught:
        core.submit(fail, 0.01)
    assert str(caught.value) == "RPC task raised ValueError: same failure"
    assert caught.value.error_code == "GUI_TASK_FAILED"


@pytest.mark.unit
def test_telemetry_and_completion_callback_failures_do_not_leak_owner_key() -> None:
    harness = _Harness()
    core = harness.core(
        emit_telemetry=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("telemetry unavailable")
        )
    )
    results: list[str] = []
    errors: list[BaseException] = []
    thread = threading.Thread(
        target=_capture,
        args=(
            lambda: core.submit(
                lambda: "done",
                1.0,
                session_id="owner",
                request_id="callback-failure",
                on_complete=lambda *_args: (_ for _ in ()).throw(
                    RuntimeError("observer unavailable")
                ),
            ),
            results,
            errors,
        ),
    )
    thread.start()
    _wait_until(lambda: core.pending_count == 1)
    core.drain_one()
    thread.join(timeout=1.0)

    assert results == ["done"]
    assert errors == []
    assert core.pending_count == 0
    assert core.cancel_request("owner", "callback-failure") == "not_queued"


@pytest.mark.unit
def test_exact_owner_key_cancels_pending_and_runs_callback_before_wake() -> None:
    harness = _Harness()
    core = harness.core()
    executed: list[bool] = []
    completions: list[tuple[str, bool]] = []
    results: list[Any] = []
    errors: list[BaseException] = []
    thread = threading.Thread(
        target=_capture,
        args=(
            lambda: core.submit(
                lambda: executed.append(True),
                2.0,
                session_id="owner",
                request_id="request",
                on_complete=lambda request_id, outcome: completions.append(
                    (request_id, outcome.ok)
                ),
            ),
            results,
            errors,
        ),
    )
    thread.start()
    _wait_until(lambda: core.pending_count == 1)

    assert core.cancel_request("foreign", "request") == "not_queued"
    assert core.cancel_request("owner", "request") == "cancelled_pending"
    thread.join(timeout=1.0)
    core.drain_one()

    assert executed == []
    assert results == []
    assert len(errors) == 1 and isinstance(errors[0], GuiTaskError)
    assert completions == [("request", False)]
    assert core.pending_count == 0
    assert core.cancel_request("owner", "request") == "not_queued"


@pytest.mark.unit
def test_timeout_before_execution_removes_request_permanently() -> None:
    harness = _Harness()
    core = harness.core()
    executed: list[bool] = []
    errors: list[BaseException] = []
    thread = threading.Thread(
        target=_capture,
        args=(
            lambda: core.submit(lambda: executed.append(True), 0.02),
            [],
            errors,
        ),
    )
    thread.start()
    thread.join(timeout=1.0)
    core.drain_one()

    assert len(errors) == 1 and isinstance(errors[0], GuiDispatchTimeout)
    assert errors[0].error_code == "GUI_TIMEOUT_BEFORE_EXECUTION"
    assert executed == []
    assert core.pending_count == 0


@pytest.mark.unit
def test_running_timeout_quarantines_until_late_completion() -> None:
    harness = _Harness()
    core = harness.core()
    started = threading.Event()
    release = threading.Event()
    first_errors: list[BaseException] = []
    completions = []

    def slow() -> str:
        started.set()
        release.wait(1.0)
        return "late"

    submitter = threading.Thread(
        target=_capture,
        args=(
            lambda: core.submit(
                slow,
                0.02,
                on_complete=lambda _request_id, outcome: completions.append(outcome),
            ),
            [],
            first_errors,
        ),
    )
    submitter.start()
    _wait_until(lambda: core.pending_count == 1)

    def drain_as_owner() -> None:
        harness.owner = threading.get_ident()
        core.drain_one()

    drainer = threading.Thread(target=drain_as_owner)
    drainer.start()
    assert started.wait(1.0)
    submitter.join(timeout=1.0)

    assert len(first_errors) == 1
    assert isinstance(first_errors[0], GuiDispatchTimeout)
    assert first_errors[0].error_code == "GUI_TIMEOUT_DURING_EXECUTION"
    with pytest.raises(GuiBusyAfterTimeout):
        # Force the admission path even though this test thread owns the harness.
        core._is_gui_thread = lambda: False
        core.submit(lambda: None, 0.01)

    release.set()
    drainer.join(timeout=1.0)
    assert len(completions) == 1
    assert completions[0].late is True
    harness.owner = threading.get_ident()
    core._is_gui_thread = harness.is_gui_thread
    results: list[str] = []
    errors: list[BaseException] = []
    recovered = threading.Thread(
        target=_capture,
        args=(lambda: core.submit(lambda: "recovered", 1.0), results, errors),
    )
    recovered.start()
    _wait_until(lambda: core.pending_count == 1)
    core.drain_one()
    recovered.join(timeout=1.0)
    assert results == ["recovered"]
    assert errors == []
    assert "gui_execution_late_completed" in harness.events


@pytest.mark.unit
def test_stop_and_injected_wake_failures_release_all_waiters() -> None:
    harness = _Harness()
    core = harness.core()
    errors: list[BaseException] = []
    threads = [
        threading.Thread(
            target=_capture,
            args=(lambda: core.submit(lambda: None, None), [], errors),
        )
        for _ in range(2)
    ]
    for expected, thread in enumerate(threads, start=1):
        thread.start()
        _wait_until(lambda count=expected: core.pending_count == count)
    core.stop_accepting()
    for thread in threads:
        thread.join(timeout=1.0)
    assert len(errors) == 2 and all(isinstance(exc, GuiTaskError) for exc in errors)
    assert core.pending_count == 0

    rejected: list[BaseException] = []
    thread = threading.Thread(
        target=_capture,
        args=(lambda: core.submit(lambda: None, 0.1), [], rejected),
    )
    thread.start()
    thread.join(timeout=1.0)
    assert len(rejected) == 1 and isinstance(rejected[0], GuiDispatchError)

    owner_executed: list[bool] = []
    with pytest.raises(GuiDispatchError, match="stopping"):
        core.submit(lambda: owner_executed.append(True), 0.01)
    assert owner_executed == []

    broken = harness.core(wake_gui=lambda: (_ for _ in ()).throw(RuntimeError("wake")))
    wake_errors: list[BaseException] = []
    thread = threading.Thread(
        target=_capture,
        args=(lambda: broken.submit(lambda: None, None), [], wake_errors),
    )
    thread.start()
    thread.join(timeout=1.0)
    assert len(wake_errors) == 1 and type(wake_errors[0]) is GuiDispatchError
    assert str(wake_errors[0]) == "Could not wake the GUI dispatcher"
    assert wake_errors[0].execution_started is False
    assert broken.pending_count == 0


@pytest.mark.unit
def test_busy_scheduler_failure_cancels_instead_of_stranding_waiter() -> None:
    harness = _Harness()
    harness.busy = True
    core = harness.core(
        schedule_wake=lambda _delay, _callback: (_ for _ in ()).throw(
            RuntimeError("scheduler unavailable")
        )
    )
    errors: list[BaseException] = []
    thread = threading.Thread(
        target=_capture,
        args=(lambda: core.submit(lambda: None, None), [], errors),
    )
    thread.start()
    _wait_until(lambda: core.pending_count == 1)
    core.drain_one()
    thread.join(timeout=1.0)

    assert len(errors) == 1 and isinstance(errors[0], GuiTaskError)
    assert core.pending_count == 0


@pytest.mark.unit
def test_busy_probe_cannot_requeue_work_after_stop_accepting() -> None:
    harness = _Harness()
    busy_entered = threading.Event()
    release_busy = threading.Event()
    executed: list[bool] = []
    scheduled: list[object] = []

    def blocked_busy() -> bool:
        busy_entered.set()
        release_busy.wait(1.0)
        return True

    core = harness.core(
        gui_busy=blocked_busy,
        schedule_wake=lambda _delay, callback: scheduled.append(callback),
    )
    errors: list[BaseException] = []
    submitter = threading.Thread(
        target=_capture,
        args=(lambda: core.submit(lambda: executed.append(True), None), [], errors),
    )
    submitter.start()
    _wait_until(lambda: core.pending_count == 1)

    def drain_as_owner() -> None:
        harness.owner = threading.get_ident()
        core.drain_one()

    drainer = threading.Thread(target=drain_as_owner)
    drainer.start()
    assert busy_entered.wait(1.0)
    core.stop_accepting()
    release_busy.set()
    drainer.join(timeout=1.0)
    submitter.join(timeout=1.0)

    assert executed == []
    assert scheduled == []
    assert core.pending_count == 0
    assert len(errors) == 1 and isinstance(errors[0], GuiTaskError)


@pytest.mark.unit
def test_clear_busy_probe_cannot_start_work_after_stop_accepting() -> None:
    harness = _Harness()
    busy_entered = threading.Event()
    release_busy = threading.Event()
    executed: list[bool] = []

    def blocked_clear_busy() -> bool:
        busy_entered.set()
        release_busy.wait(1.0)
        return False

    core = harness.core(gui_busy=blocked_clear_busy)
    errors: list[BaseException] = []
    submitter = threading.Thread(
        target=_capture,
        args=(lambda: core.submit(lambda: executed.append(True), None), [], errors),
    )
    submitter.start()
    _wait_until(lambda: core.pending_count == 1)

    def drain_as_owner() -> None:
        harness.owner = threading.get_ident()
        core.drain_one()

    drainer = threading.Thread(target=drain_as_owner)
    drainer.start()
    assert busy_entered.wait(1.0)
    core.stop_accepting()
    release_busy.set()
    drainer.join(timeout=1.0)
    submitter.join(timeout=1.0)

    assert executed == []
    assert core.pending_count == 0
    assert len(errors) == 1 and isinstance(errors[0], GuiTaskError)


@pytest.mark.unit
def test_dispatch_gui_modules_have_no_framework_or_upward_imports() -> None:
    dispatch_dir = Path(__file__).parents[1] / "addon" / "FreeCADMCP" / "dispatch"
    forbidden = {
        "FreeCAD",
        "FreeCADGui",
        "PySide",
        "PySide2",
        "PySide6",
        "addon.FreeCADMCP.rpc_server",
        "addon.FreeCADMCP.runtime",
        "addon.FreeCADMCP.transport",
    }
    paths = sorted(dispatch_dir.glob("gui_*.py"))
    assert paths
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        assert not {
            name
            for name in imports
            if any(name == item or name.startswith(item + ".") for item in forbidden)
        }, path


@pytest.mark.unit
def test_canonical_submit_helper_surface_operates_on_pure_core() -> None:
    expected = {
        "build_gui_request",
        "emit_gui_queued_telemetry",
        "execute_request",
        "unwrap_outcome",
        "execute_on_gui_thread",
        "enqueue_gui_request",
        "wait_for_request_completion",
        "forget_cancelled_request",
        "cancel_pending_after_timeout",
        "quarantine_running_timeout",
        "wait_for_race_winner",
        "raise_submit_timeout_error",
        "handle_submit_timeout",
        "finalize_completed_request",
    }
    assert all(callable(getattr(gui_submit, name)) for name in expected)
    expected_parameters = {
        "build_gui_request": ("callable_", "request_id", "session_id", "on_complete"),
        "emit_gui_queued_telemetry": ("request", "timeout"),
        "execute_request": ("request",),
        "unwrap_outcome": ("outcome", "request"),
        "execute_on_gui_thread": ("dispatcher", "request"),
        "enqueue_gui_request": ("dispatcher", "request"),
        "wait_for_request_completion": ("request", "timeout"),
        "forget_cancelled_request": ("dispatcher", "request"),
        "cancel_pending_after_timeout": ("dispatcher", "request"),
        "quarantine_running_timeout": ("dispatcher", "request"),
        "wait_for_race_winner": ("request",),
        "raise_submit_timeout_error": ("request", "timeout", "before_execution"),
        "handle_submit_timeout": ("dispatcher", "request", "timeout"),
        "finalize_completed_request": ("request",),
    }
    assert {
        name: tuple(inspect.signature(getattr(gui_submit, name)).parameters)
        for name in expected
    } == expected_parameters

    harness = _Harness()
    request = gui_submit.build_gui_request(
        lambda: "helper-result",
        request_id="helper",
        session_id="owner",
        on_complete=None,
    )
    request._emit_telemetry = harness.emit
    gui_submit.emit_gui_queued_telemetry(request, 2.0)
    assert "gui_execution_queued" in harness.events
    assert gui_submit.execute_on_gui_thread(object(), request) == "helper-result"
    assert gui_submit.finalize_completed_request(request) == "helper-result"

    control = gui_submit.build_gui_request(
        lambda: (_ for _ in ()).throw(SystemExit(3)),
        request_id="control",
        session_id=None,
        on_complete=None,
    )
    with pytest.raises(SystemExit):
        gui_submit.execute_request(control)


@pytest.mark.unit
def test_operational_core_propagates_control_exceptions_and_releases_waiter() -> None:
    harness = _Harness()
    core = harness.core()
    with pytest.raises(SystemExit):
        core.submit(lambda: (_ for _ in ()).throw(SystemExit(4)), 0.01)

    errors: list[BaseException] = []
    submitter = threading.Thread(
        target=_capture,
        args=(
            lambda: core.submit(
                lambda: (_ for _ in ()).throw(KeyboardInterrupt()),
                None,
                session_id="owner",
                request_id="control",
            ),
            [],
            errors,
        ),
    )
    submitter.start()
    _wait_until(lambda: core.pending_count == 1)
    with pytest.raises(KeyboardInterrupt):
        core.drain_one()
    submitter.join(timeout=1.0)

    assert len(errors) == 1 and isinstance(errors[0], GuiTaskError)
    assert "KeyboardInterrupt" in str(errors[0])
    assert core.pending_count == 0
    assert core.cancel_request("owner", "control") == "not_queued"

    recovered: list[str] = []
    recovered_errors: list[BaseException] = []
    recovery = threading.Thread(
        target=_capture,
        args=(
            lambda: core.submit(lambda: "recovered", 1.0),
            recovered,
            recovered_errors,
        ),
    )
    recovery.start()
    _wait_until(lambda: core.pending_count == 1)
    core.drain_one()
    recovery.join(timeout=1.0)
    assert recovered == ["recovered"]
    assert recovered_errors == []


@pytest.mark.unit
def test_control_exception_wakes_the_next_already_queued_request() -> None:
    harness = _Harness()
    core = harness.core()
    first_errors: list[BaseException] = []
    second_results: list[str] = []
    second_errors: list[BaseException] = []
    first = threading.Thread(
        target=_capture,
        args=(
            lambda: core.submit(
                lambda: (_ for _ in ()).throw(SystemExit(5)),
                None,
            ),
            [],
            first_errors,
        ),
    )
    second = threading.Thread(
        target=_capture,
        args=(
            lambda: core.submit(lambda: "second", 1.0),
            second_results,
            second_errors,
        ),
    )
    first.start()
    _wait_until(lambda: core.pending_count == 1)
    second.start()
    _wait_until(lambda: core.pending_count == 2)

    wakes_before = len(harness.wakes)
    with pytest.raises(SystemExit):
        core.drain_one()
    assert len(harness.wakes) == wakes_before + 1
    core.drain_one()
    first.join(timeout=1.0)
    second.join(timeout=1.0)

    assert len(first_errors) == 1 and isinstance(first_errors[0], GuiTaskError)
    assert second_results == ["second"]
    assert second_errors == []


@pytest.mark.unit
def test_qt_adapter_preserves_legacy_direct_submit_shape() -> None:
    from PySide import QtCore

    from addon.FreeCADMCP.rpc_server.gui_dispatcher_qt import GuiDispatcher

    QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])
    dispatcher = GuiDispatcher()
    assert dispatcher.submit(lambda: "direct", 0.01) == "direct"
    assert dispatcher.pending_count == 0
