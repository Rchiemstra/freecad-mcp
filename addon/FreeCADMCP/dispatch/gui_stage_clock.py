"""Monotonic stage clocks for GUI dispatch latency instrumentation."""

from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

_ACTIVE_CLOCK: ContextVar[GuiStageClock | None] = ContextVar(
    "freecad_mcp_gui_stage_clock", default=None
)

_STAGE_FIELDS = (
    "queue_wait_ms",
    "defer_wait_ms",
    "admission_ms",
    "mutation_callback_ms",
    "native_commit_ms",
    "postcondition_ms",
    "presentation_ms",
    "screenshot_ms",
)


def _elapsed_ms(start: float | None, end: float | None) -> float | None:
    if start is None or end is None:
        return None
    return max(0.0, (end - start) * 1000.0)


@dataclass
class GuiStageClock:
    """Per-request monotonic stage timings for GUI dispatch telemetry."""

    submitted_at: float = field(default_factory=time.monotonic)
    queued_at: float | None = None
    deferred_at: float | None = None
    running_at: float | None = None
    response_at: float | None = None
    mutation_started: bool = False
    completion_uncertain: bool = False
    timeout_stage: str | None = None
    error_code: str | None = None
    outstanding_at_submit: int = 0
    _defer_accum_s: float = 0.0
    _defer_started_at: float | None = None
    _admission_started_at: float | None = None
    _mutation_started_at: float | None = None
    _native_commit_started_at: float | None = None
    _postcondition_started_at: float | None = None
    _presentation_started_at: float | None = None
    _screenshot_started_at: float | None = None
    queue_wait_ms: float | None = None
    defer_wait_ms: float | None = None
    admission_ms: float | None = None
    mutation_callback_ms: float | None = None
    native_commit_ms: float | None = None
    postcondition_ms: float | None = None
    presentation_ms: float | None = None
    screenshot_ms: float | None = None
    response_total_ms: float | None = None

    def mark_queued(self) -> None:
        if self.queued_at is None:
            self.queued_at = self.submitted_at

    def mark_drain_started(self) -> None:
        now = time.monotonic()
        if self.queue_wait_ms is None:
            self.queue_wait_ms = _elapsed_ms(self.submitted_at, now)

    def mark_deferred(self) -> None:
        now = time.monotonic()
        self.deferred_at = now
        if self._defer_started_at is None:
            self._defer_started_at = now

    def mark_requeued(self) -> None:
        if self._defer_started_at is not None:
            self._defer_accum_s += time.monotonic() - self._defer_started_at
            self._defer_started_at = None
            self.defer_wait_ms = self._defer_accum_s * 1000.0

    def mark_running(self) -> None:
        now = time.monotonic()
        self.running_at = now
        self.mark_requeued()
        if self.queue_wait_ms is None:
            self.queue_wait_ms = _elapsed_ms(self.submitted_at, now)

    def begin_admission(self) -> None:
        self._admission_started_at = time.monotonic()

    def end_admission(self) -> None:
        if self._admission_started_at is not None:
            self.admission_ms = _elapsed_ms(self._admission_started_at, time.monotonic())
            self._admission_started_at = None

    def begin_mutation_callback(self) -> None:
        now = time.monotonic()
        if self._admission_started_at is not None:
            self.admission_ms = _elapsed_ms(self._admission_started_at, now)
            self._admission_started_at = None
        self._mutation_started_at = now
        self.mutation_started = True

    def end_mutation_callback(self) -> None:
        if self._mutation_started_at is not None:
            self.mutation_callback_ms = _elapsed_ms(
                self._mutation_started_at, time.monotonic()
            )
            self._mutation_started_at = None

    def begin_native_commit(self) -> None:
        now = time.monotonic()
        if self._mutation_started_at is not None:
            self.mutation_callback_ms = _elapsed_ms(self._mutation_started_at, now)
            self._mutation_started_at = None
        self._native_commit_started_at = now

    def end_native_commit(self) -> None:
        if self._native_commit_started_at is not None:
            self.native_commit_ms = _elapsed_ms(
                self._native_commit_started_at, time.monotonic()
            )
            self._native_commit_started_at = None

    def begin_postcondition(self) -> None:
        self._postcondition_started_at = time.monotonic()

    def end_postcondition(self) -> None:
        if self._postcondition_started_at is not None:
            self.postcondition_ms = _elapsed_ms(
                self._postcondition_started_at, time.monotonic()
            )
            self._postcondition_started_at = None

    def begin_presentation(self) -> None:
        self._presentation_started_at = time.monotonic()

    def end_presentation(self) -> None:
        if self._presentation_started_at is not None:
            self.presentation_ms = _elapsed_ms(
                self._presentation_started_at, time.monotonic()
            )
            self._presentation_started_at = None

    def begin_screenshot(self) -> None:
        self._screenshot_started_at = time.monotonic()

    def end_screenshot(self) -> None:
        if self._screenshot_started_at is not None:
            self.screenshot_ms = _elapsed_ms(
                self._screenshot_started_at, time.monotonic()
            )
            self._screenshot_started_at = None

    def begin_non_mutation_execution(self) -> None:
        """Treat a plain GUI callable as mutation_callback when no native commit runs."""

        if self._admission_started_at is not None:
            self.admission_ms = _elapsed_ms(
                self._admission_started_at, time.monotonic()
            )
            self._admission_started_at = None
        if self._mutation_started_at is None:
            self._mutation_started_at = time.monotonic()

    def end_non_mutation_execution(self) -> None:
        self.end_mutation_callback()

    def close_open_stages(self, *, now: float | None = None) -> None:
        """Snapshot elapsed time for any stage still in progress."""

        end = now if now is not None else time.monotonic()
        if self.queue_wait_ms is None:
            if self.running_at is not None:
                self.queue_wait_ms = _elapsed_ms(self.submitted_at, self.running_at)
            else:
                self.queue_wait_ms = _elapsed_ms(self.submitted_at, end)
        if self._defer_started_at is not None:
            self._defer_accum_s += end - self._defer_started_at
            self._defer_started_at = None
            self.defer_wait_ms = self._defer_accum_s * 1000.0
        if self._admission_started_at is not None:
            self.admission_ms = _elapsed_ms(self._admission_started_at, end)
            self._admission_started_at = None
        if self._mutation_started_at is not None:
            self.mutation_callback_ms = _elapsed_ms(self._mutation_started_at, end)
            self._mutation_started_at = None
        if self._native_commit_started_at is not None:
            self.native_commit_ms = _elapsed_ms(self._native_commit_started_at, end)
            self._native_commit_started_at = None
        if self._postcondition_started_at is not None:
            self.postcondition_ms = _elapsed_ms(self._postcondition_started_at, end)
            self._postcondition_started_at = None
        if self._presentation_started_at is not None:
            self.presentation_ms = _elapsed_ms(self._presentation_started_at, end)
            self._presentation_started_at = None
        if self._screenshot_started_at is not None:
            self.screenshot_ms = _elapsed_ms(self._screenshot_started_at, end)
            self._screenshot_started_at = None

    def finalize(
        self,
        *,
        timeout_stage: str | None = None,
        completion_uncertain: bool | None = None,
        error_code: str | None = None,
    ) -> None:
        if timeout_stage is not None:
            self.timeout_stage = timeout_stage
        if completion_uncertain is not None:
            self.completion_uncertain = completion_uncertain
        if error_code is not None:
            self.error_code = error_code
        now = time.monotonic()
        self.close_open_stages(now=now)
        self.response_at = now
        self.response_total_ms = _elapsed_ms(self.submitted_at, now)

    def measured_stage_sum_ms(self) -> float:
        total = 0.0
        for name in _STAGE_FIELDS:
            value = getattr(self, name)
            if value is not None:
                total += float(value)
        return total

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "queued_at": self.queued_at,
            "deferred_at": self.deferred_at,
            "running_at": self.running_at,
            "response_at": self.response_at,
            "mutation_started": self.mutation_started,
            "completion_uncertain": self.completion_uncertain,
            "timeout_stage": self.timeout_stage,
            "error_code": self.error_code,
            "outstanding_at_submit": self.outstanding_at_submit,
            "response_total_ms": self.response_total_ms,
        }
        for name in _STAGE_FIELDS:
            payload[name] = getattr(self, name)
        return payload


def current_stage_clock() -> GuiStageClock | None:
    return _ACTIVE_CLOCK.get()


@contextmanager
def stage_clock_scope(clock: GuiStageClock | None):
    if clock is None:
        yield
        return
    token = _ACTIVE_CLOCK.set(clock)
    try:
        yield
    finally:
        _ACTIVE_CLOCK.reset(token)


@contextmanager
def record_presentation():
    clock = current_stage_clock()
    if clock is None:
        yield
        return
    clock.begin_presentation()
    try:
        yield
    finally:
        clock.end_presentation()


@contextmanager
def record_screenshot():
    clock = current_stage_clock()
    if clock is None:
        yield
        return
    clock.begin_screenshot()
    try:
        yield
    finally:
        clock.end_screenshot()


__all__ = [
    "GuiStageClock",
    "current_stage_clock",
    "record_presentation",
    "record_screenshot",
    "stage_clock_scope",
]
