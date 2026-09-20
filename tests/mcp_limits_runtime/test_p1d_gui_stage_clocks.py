"""Phase 1d GUI stage-clock instrumentation contracts (Docker-runnable fakes)."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from addon.FreeCADMCP.dispatch.gui_core import GuiDispatchCore
from addon.FreeCADMCP.dispatch.gui_errors import (
    GuiBusyAfterTimeout,
    GuiDispatchTimeout,
)

pytestmark = pytest.mark.unit

_GUI_RPC_TIMEOUT_S = 30
_EPSILON_MS = 5.0
_MS_STAGE_FIELDS = (
    "queue_wait_ms",
    "defer_wait_ms",
    "admission_ms",
    "mutation_callback_ms",
    "native_commit_ms",
    "postcondition_ms",
    "presentation_ms",
    "response_total_ms",
    "screenshot_ms",
)
_REQUIRED_STAGE_FIELDS = _MS_STAGE_FIELDS + (
    "timeout_stage",
    "mutation_started",
    "completion_uncertain",
    "error_code",
)


class _Harness:
    def __init__(self) -> None:
        self.owner = threading.get_ident()
        self.events: list[dict[str, Any]] = []
        self.busy = False

    def is_gui_thread(self) -> bool:
        return threading.get_ident() == self.owner

    def drain_as_owner(self, core: GuiDispatchCore) -> None:
        self.owner = threading.get_ident()
        core.drain_one()

    def wake(self) -> None:
        return None

    def schedule(self, _delay_ms: int, callback) -> None:
        callback()

    def emit(self, _source: str, event: str, **fields: Any) -> None:
        self.events.append({"event": event, **fields})

    def core(self) -> GuiDispatchCore:
        return GuiDispatchCore(
            is_gui_thread=self.is_gui_thread,
            wake_gui=self.wake,
            schedule_wake=self.schedule,
            gui_busy=lambda: self.busy,
            emit_telemetry=self.emit,
        )


def _wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.001)
    assert predicate()


def _terminal_event(harness: _Harness) -> dict[str, Any]:
    for entry in reversed(harness.events):
        if entry["event"] in {
            "gui_execution_completed",
            "gui_execution_timeout",
            "gui_execution_late_completed",
        }:
            return entry
    raise AssertionError(f"no terminal telemetry event in {harness.events}")


def _stage_payload(entry: dict[str, Any]) -> dict[str, Any]:
    payload = dict(entry.get("payload") or {})
    response_total = payload.get("response_total_ms")
    assert entry.get("duration_ms") == response_total, (
        "duration_ms must equal response_total_ms on terminal telemetry"
    )
    for field in _REQUIRED_STAGE_FIELDS:
        assert field in payload, f"missing stage field {field} in {payload}"
    return payload


def _wait_for_event(harness: _Harness, event_name: str, timeout: float = 2.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for entry in harness.events:
            if entry.get("event") == event_name:
                return entry
        time.sleep(0.001)
    raise AssertionError(
        f"timed out waiting for {event_name!r}; saw {[e.get('event') for e in harness.events]}"
    )


def _ms(value: object) -> float:
    return 0.0 if value is None else float(value)


def test_baseline_terminal_telemetry_exposes_stage_fields_and_duration() -> None:
    harness = _Harness()
    core = harness.core()
    assert core.submit(lambda: "ok", 1.0) == "ok"
    _stage_payload(_terminal_event(harness))


def test_nested_native_commit_topology_matches_response_total() -> None:
    harness = _Harness()
    core = harness.core()

    def task() -> str:
        from addon.FreeCADMCP.dispatch.gui_stage_clock import current_stage_clock

        active = current_stage_clock()
        assert active is not None
        active.begin_admission()
        time.sleep(0.02)
        active.end_admission()
        active.begin_native_commit()
        time.sleep(0.01)
        active.begin_mutation_callback()
        time.sleep(0.03)
        active.end_mutation_callback()
        time.sleep(0.01)
        active.begin_postcondition()
        time.sleep(0.02)
        active.end_postcondition()
        active.end_native_commit()
        return "done"

    thread = threading.Thread(target=lambda: core.submit(task, 2.0))
    thread.start()
    _wait_until(lambda: core.pending_count == 1)
    drainer = threading.Thread(target=lambda: harness.drain_as_owner(core))
    drainer.start()
    drainer.join(timeout=2.0)
    thread.join(timeout=2.0)
    entry = _terminal_event(harness)
    payload = _stage_payload(entry)
    pre_commit = (
        _ms(payload["queue_wait_ms"])
        + _ms(payload["defer_wait_ms"])
        + _ms(payload["admission_ms"])
    )
    nested = _ms(payload["mutation_callback_ms"]) + _ms(payload["postcondition_ms"])
    native_commit = _ms(payload["native_commit_ms"])
    response_total = _ms(payload["response_total_ms"])
    assert nested <= native_commit + _EPSILON_MS
    assert pre_commit + native_commit <= response_total + _EPSILON_MS
    assert entry["duration_ms"] == response_total


def test_timeout_during_open_native_commit_closes_native_commit_ms() -> None:
    harness = _Harness()
    core = harness.core()
    hold = threading.Event()
    started = threading.Event()
    slow_errors: list[BaseException] = []
    request_timeout_s = 0.05

    def slow_task() -> None:
        from addon.FreeCADMCP.dispatch.gui_stage_clock import current_stage_clock

        started.set()
        active = current_stage_clock()
        assert active is not None
        active.begin_admission()
        active.end_admission()
        active.begin_native_commit()
        hold.wait(timeout=float(_GUI_RPC_TIMEOUT_S) + 1.0)
        active.end_native_commit()

    def slow_runner() -> None:
        try:
            core.submit(slow_task, request_timeout_s)
        except BaseException as exc:
            slow_errors.append(exc)

    slow_thread = threading.Thread(target=slow_runner)
    slow_thread.start()
    _wait_until(lambda: core.pending_count == 1)
    drainer = threading.Thread(target=lambda: harness.drain_as_owner(core))
    drainer.start()
    assert started.wait(timeout=2.0)
    slow_thread.join(timeout=2.0)
    assert len(slow_errors) == 1
    assert isinstance(slow_errors[0], GuiDispatchTimeout)
    timeout_entry = _wait_for_event(harness, "gui_execution_timeout")
    payload = dict(timeout_entry.get("payload") or {})
    response_total = payload.get("response_total_ms")
    assert timeout_entry.get("duration_ms") == response_total
    assert payload["timeout_stage"] == "during_execution"
    assert payload["completion_uncertain"] is True
    assert payload["mutation_started"] is False
    assert payload["native_commit_ms"] is not None
    assert _ms(payload["native_commit_ms"]) > 0.0
    hold.set()
    drainer.join(timeout=2.0)


def test_injected_31s_native_commit_maps_timed_out_uncertain() -> None:
    harness = _Harness()
    core = harness.core()
    hold = threading.Event()
    started = threading.Event()
    slow_errors: list[BaseException] = []
    request_timeout_s = 0.05

    def slow_task() -> None:
        started.set()
        hold.wait(timeout=float(_GUI_RPC_TIMEOUT_S) + 1.0)

    def slow_runner() -> None:
        try:
            core.submit(slow_task, request_timeout_s)
        except BaseException as exc:
            slow_errors.append(exc)

    slow_thread = threading.Thread(target=slow_runner)
    slow_thread.start()
    _wait_until(lambda: core.pending_count == 1)
    drainer = threading.Thread(target=lambda: harness.drain_as_owner(core))
    drainer.start()
    assert started.wait(timeout=2.0)
    slow_thread.join(timeout=2.0)
    hold.set()
    drainer.join(timeout=2.0)
    assert len(slow_errors) == 1
    exc = slow_errors[0]
    assert isinstance(exc, GuiDispatchTimeout)
    assert exc.error_code == "GUI_TIMEOUT_DURING_EXECUTION"
    assert exc.completion_uncertain is True
    assert _GUI_RPC_TIMEOUT_S == 30
    payload = _stage_payload(_terminal_event(harness))
    assert payload["completion_uncertain"] is True
    assert payload["timeout_stage"] == "during_execution"


def test_short_timeout_before_execution_when_never_started() -> None:
    harness = _Harness()
    core = harness.core()
    errors: list[BaseException] = []

    def runner() -> None:
        try:
            core.submit(lambda: "late", 0.3)
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=runner)
    thread.start()
    _wait_until(lambda: core.pending_count == 1)
    thread.join(timeout=1.0)
    assert len(errors) == 1
    exc = errors[0]
    assert isinstance(exc, GuiDispatchTimeout)
    assert exc.error_code == "GUI_TIMEOUT_BEFORE_EXECUTION"
    assert exc.execution_started is False
    payload = _stage_payload(_terminal_event(harness))
    assert payload["timeout_stage"] == "before_execution"
    assert payload["mutation_started"] is False


def test_outstanding_two_second_request_records_queue_wait() -> None:
    harness = _Harness()
    core = harness.core()
    gate = threading.Event()
    first_started = threading.Event()

    def first() -> str:
        first_started.set()
        gate.wait(timeout=5.0)
        return "first"

    def second() -> str:
        return "second"

    first_thread = threading.Thread(target=lambda: core.submit(first, 5.0))
    second_thread = threading.Thread(target=lambda: core.submit(second, 5.0))
    first_thread.start()
    _wait_until(lambda: core.pending_count == 1)
    drainer = threading.Thread(target=lambda: harness.drain_as_owner(core))
    drainer.start()
    assert first_started.wait(timeout=2.0)
    second_thread.start()
    _wait_until(lambda: core.pending_count == 1)
    time.sleep(0.05)
    gate.set()
    first_thread.join(timeout=5.0)
    drainer.join(timeout=5.0)
    second_drainer = threading.Thread(target=lambda: harness.drain_as_owner(core))
    second_drainer.start()
    second_thread.join(timeout=5.0)
    second_drainer.join(timeout=5.0)
    completed = [
        entry
        for entry in harness.events
        if entry["event"] == "gui_execution_completed"
    ]
    assert len(completed) == 2
    completed_payloads = [_stage_payload(entry) for entry in completed]
    second_payload = max(
        completed_payloads,
        key=lambda payload: _ms(payload.get("queue_wait_ms")),
    )
    assert _ms(second_payload.get("queue_wait_ms")) > 0.0


def test_quarantined_second_request_reports_gui_busy_after_timeout() -> None:
    harness = _Harness()
    core = harness.core()
    hold = threading.Event()
    slow_started = threading.Event()
    slow_errors: list[BaseException] = []
    errors: list[BaseException] = []

    def slow() -> None:
        slow_started.set()
        hold.wait(timeout=5.0)

    def slow_runner() -> None:
        try:
            core.submit(slow, 0.2)
        except BaseException as exc:
            slow_errors.append(exc)

    def blocked() -> None:
        try:
            core.submit(lambda: "never", 1.0)
        except BaseException as exc:
            errors.append(exc)

    slow_thread = threading.Thread(target=slow_runner)
    slow_thread.start()
    _wait_until(lambda: core.pending_count == 1)
    drainer = threading.Thread(target=lambda: harness.drain_as_owner(core))
    drainer.start()
    assert slow_started.wait(timeout=2.0)
    slow_thread.join(timeout=2.0)
    assert len(slow_errors) == 1
    assert isinstance(slow_errors[0], GuiDispatchTimeout)
    assert slow_errors[0].error_code == "GUI_TIMEOUT_DURING_EXECUTION"
    blocked_thread = threading.Thread(target=blocked)
    blocked_thread.start()
    blocked_thread.join(timeout=2.0)
    hold.set()
    drainer.join(timeout=2.0)
    assert len(errors) == 1
    assert isinstance(errors[0], GuiBusyAfterTimeout)
    assert errors[0].error_code == "GUI_BUSY_AFTER_TIMEOUT"
    queued = [
        entry
        for entry in harness.events
        if entry["event"] == "gui_execution_queued"
    ]
    assert len(queued) >= 2
    blocked_queued = queued[-1]
    blocked_payload = blocked_queued.get("payload") or {}
    assert blocked_payload.get("outstanding_at_submit") == 1
