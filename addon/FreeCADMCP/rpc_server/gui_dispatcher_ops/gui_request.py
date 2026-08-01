"""Mutable per-request state for GUI dispatch."""

from __future__ import annotations

import contextlib
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..telemetry import emit as emit_telemetry
from .gui_outcome import GuiOutcome


@dataclass(eq=False)
class GuiRequest:
    callable: Callable[[], Any]
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str | None = None
    on_complete: Callable[[str, GuiOutcome], None] | None = field(
        default=None, repr=False
    )
    completion: threading.Event = field(default_factory=threading.Event)
    outcome: GuiOutcome | None = None
    state: str = "pending"
    submitted_at: float = field(default_factory=time.monotonic)
    _state_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def mark_running(self) -> bool:
        with self._state_lock:
            if self.state != "pending":
                return False
            self.state = "running"
            return True

    def cancel_if_pending(self, before_wake: Callable[[], None] | None = None) -> bool:
        callback = None
        outcome = None
        with self._state_lock:
            if self.state != "pending":
                return False
            self.state = "cancelled"
            self.outcome = GuiOutcome(False, error="GUI request cancelled before execution")
            outcome = self.outcome
            callback = self.on_complete
        if callback is not None:
            with contextlib.suppress(Exception):
                callback(self.request_id, outcome)
        if before_wake is not None:
            before_wake()
        # The waiting handler must never observe completion before attribution,
        # cancellation resolution, and late-result journaling have finished.
        self.completion.set()
        return True

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
    ) -> None:
        callback = None
        with self._state_lock:
            previous_state = self.state
            self.outcome = outcome
            self.state = "completed"
            callback = self.on_complete
        emit_telemetry(
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
                # Completion reporting must never destabilize the GUI queue.
                callback(self.request_id, outcome)
        if before_wake is not None:
            before_wake()
        self.completion.set()
