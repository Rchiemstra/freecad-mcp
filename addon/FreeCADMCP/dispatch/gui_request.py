"""Thread-safe state for one GUI dispatch request."""

from __future__ import annotations

import contextlib
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .gui_outcome import GuiOutcome

TelemetryCallback = Callable[..., object]


@dataclass(frozen=True)
class GuiDeferDecision:
    """Ask the dispatcher to retry one logical request after a native event.

    ``document_keys`` are also the ordering scope: later requests that touch
    any of those documents cannot overtake this request while it is deferred.
    The decision deliberately contains no delay or retry interval.  Only an
    explicit document readiness notification may requeue the request.
    """

    document_keys: tuple[str, ...]
    reason: str = "native_mutation_readiness"


DeferProbe = Callable[[], GuiDeferDecision | None]


@dataclass(eq=False)
class GuiRequest:
    callable: Callable[[], Any]
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str | None = None
    on_complete: Callable[[str, GuiOutcome], None] | None = field(
        default=None, repr=False
    )
    defer_probe: DeferProbe | None = field(default=None, repr=False)
    document_keys: tuple[str, ...] = ()
    completion: threading.Event = field(default_factory=threading.Event)
    outcome: GuiOutcome | None = None
    state: str = "pending"
    submitted_at: float = field(default_factory=time.monotonic)
    deadline_at: float | None = None
    _state_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _emit_telemetry: TelemetryCallback | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def mark_running(self) -> bool:
        with self._state_lock:
            if self.state != "pending":
                return False
            self.state = "running"
            return True

    def _mark_deferred(self) -> bool:
        with self._state_lock:
            if self.state != "pending":
                return False
            self.state = "deferred"
            return True

    def _requeue_if_deferred(self) -> bool:
        with self._state_lock:
            if self.state != "deferred":
                return False
            self.state = "pending"
            return True

    def cancel_if_pending(
        self,
        before_wake: Callable[[], None] | None = None,
    ) -> bool:
        callback = None
        outcome = None
        with self._state_lock:
            if self.state not in {"pending", "deferred"}:
                return False
            self.state = "cancelled"
            self.outcome = GuiOutcome(
                False,
                error="GUI request cancelled before execution",
            )
            outcome = self.outcome
            callback = self.on_complete
        if callback is not None:
            with contextlib.suppress(Exception):
                callback(self.request_id, outcome)
        try:
            if before_wake is not None:
                before_wake()
        finally:
            # Attribution and cleanup must be visible before the waiter wakes.
            self.completion.set()
        return True

    def _expire_if_waiting(
        self,
        before_wake: Callable[[], None] | None = None,
    ) -> bool:
        callback = None
        outcome = None
        with self._state_lock:
            if self.state not in {"pending", "deferred"}:
                return False
            self.state = "timed_out_pending"
            self.outcome = GuiOutcome(
                False,
                error="GUI request timed out before execution",
            )
            outcome = self.outcome
            callback = self.on_complete
        if callback is not None:
            with contextlib.suppress(Exception):
                callback(self.request_id, outcome)
        try:
            if before_wake is not None:
                before_wake()
        finally:
            self.completion.set()
        return True

    @property
    def _deadline_expired(self) -> bool:
        deadline = self.deadline_at
        return deadline is not None and time.monotonic() >= deadline

    @property
    def state_snapshot(self) -> str:
        with self._state_lock:
            return self.state

    def mark_timed_out_if_running(self) -> bool:
        with self._state_lock:
            if self.state != "running":
                return False
            self.state = "timed_out_running"
            return True

    @property
    def completed(self) -> bool:
        with self._state_lock:
            return self.state == "completed"

    def complete(
        self,
        outcome: GuiOutcome,
        before_wake: Callable[[], None] | None = None,
    ) -> bool:
        with self._state_lock:
            previous_state = self.state
            if previous_state in {
                "cancelled",
                "completed",
                "timed_out_pending",
            }:
                return False
            if previous_state == "timed_out_running" and not outcome.late:
                outcome = GuiOutcome(
                    ok=outcome.ok,
                    value=outcome.value,
                    error=outcome.error,
                    late=True,
                )
            self.outcome = outcome
            self.state = "completed"
            callback = self.on_complete
        emitter = self._emit_telemetry
        if emitter is not None:
            with contextlib.suppress(Exception):
                emitter(
                    "gui_dispatcher",
                    (
                        "gui_execution_late_completed"
                        if previous_state == "timed_out_running"
                        else "gui_execution_completed"
                    ),
                    status="succeeded" if outcome.ok else "failed",
                    error_code=None if outcome.ok else "GUI_TASK_FAILED",
                    request_id=self.request_id,
                    execution_id=self.request_id,
                    payload={"previous_state": previous_state},
                )
        if callback is not None:
            with contextlib.suppress(Exception):
                callback(self.request_id, outcome)
        try:
            if before_wake is not None:
                before_wake()
        finally:
            self.completion.set()
        return True
