"""Thread-safe mutable state shared by all phases of one RPC request."""

from __future__ import annotations

import copy
import threading
import time
import uuid
from typing import Any

from .inflight_snapshot import InflightSnapshot
from .request_cancellation_error import RequestCancellationError


class CancellationToken:
    """Thread-safe mutable state shared by all phases of one RPC request."""

    def __init__(self, session_id: str, request_id: str, method: str) -> None:
        self.session_id = str(session_id)
        self.request_id = str(request_id)
        self.method = str(method)
        self._phase = "registered"
        self._cancellation_requested = False
        self._mutation_started = False
        self._uncertain = False
        self._handler_finished = False
        self._active_gui_phases = 0
        self._terminal = False
        self._terminal_status: str | None = None
        self._cancel_requested_at: float | None = None
        self._accepting_cancellation = True
        self._cancellation_resolving = False
        self._cancellation_resolved = False
        self._cancellation_resolution: Any = None
        self._cancellation_resolution_complete = threading.Event()
        self._cancellation_begin_claimed = False
        self._cancellation_begin_complete = threading.Event()
        self._recovery_incident_id: str | None = None
        self._lock = threading.RLock()

    def _snapshot_locked(self) -> InflightSnapshot:
        return InflightSnapshot(
            session_id=self.session_id,
            request_id=self.request_id,
            method=self.method,
            phase=self._phase,
            cancellation_requested=self._cancellation_requested,
            mutation_started=self._mutation_started,
            uncertain=self._uncertain,
            handler_finished=self._handler_finished,
            active_gui_phases=self._active_gui_phases,
            terminal=self._terminal,
            terminal_status=self._terminal_status,
            cancel_requested_at=self._cancel_requested_at,
            cancellation_resolved=self._cancellation_resolved,
            recovery_incident_id=self._recovery_incident_id,
        )

    def snapshot(self) -> InflightSnapshot:
        with self._lock:
            return self._snapshot_locked()

    def set_phase(self, phase: str) -> InflightSnapshot:
        with self._lock:
            if not self._terminal:
                self._phase = str(phase)[:128]
            return self._snapshot_locked()

    def checkpoint(self, phase: str) -> InflightSnapshot:
        """Publish *phase* and fail before starting it when cancelled."""

        with self._lock:
            if not self._terminal:
                self._phase = str(phase)[:128]
            snapshot = self._snapshot_locked()
        if snapshot.cancellation_requested:
            raise RequestCancellationError(snapshot)
        return snapshot

    def request_cancel(self) -> tuple[bool, InflightSnapshot]:
        with self._lock:
            newly_requested = (
                not self._cancellation_requested
                and not self._terminal
                and self._accepting_cancellation
            )
            if not self._terminal and self._accepting_cancellation:
                self._cancellation_requested = True
                if self._cancel_requested_at is None:
                    self._cancel_requested_at = time.monotonic()
            return newly_requested, self._snapshot_locked()

    def mark_mutation_started(self, phase: str = "mutation_started") -> InflightSnapshot:
        """Conservatively record that document or file mutation may now occur."""

        with self._lock:
            self._mutation_started = True
            self._phase = str(phase)[:128]
            return self._snapshot_locked()

    def begin_mutation(self, phase: str = "mutation_started") -> InflightSnapshot:
        """Atomically reject cancellation or cross the may-mutate boundary."""

        with self._lock:
            if self._cancellation_requested:
                raise RequestCancellationError(self._snapshot_locked())
            self._mutation_started = True
            self._phase = str(phase)[:128]
            return self._snapshot_locked()

    def begin_irreversible(self, phase: str) -> InflightSnapshot:
        """Cross a non-rollbackable boundary and reject later cancellation."""

        with self._lock:
            if self._cancellation_requested:
                raise RequestCancellationError(self._snapshot_locked())
            self._mutation_started = True
            self._phase = str(phase)[:128]
            self._accepting_cancellation = False
            return self._snapshot_locked()

    def mark_uncertain(self, phase: str = "completion_uncertain") -> InflightSnapshot:
        with self._lock:
            self._uncertain = True
            self._phase = str(phase)[:128]
            if self._recovery_incident_id is None:
                self._recovery_incident_id = str(uuid.uuid4())
            return self._snapshot_locked()

    def mark_recovered(self, phase: str = "recovery_completed") -> InflightSnapshot:
        with self._lock:
            self._uncertain = False
            self._phase = str(phase)[:128]
            return self._snapshot_locked()

    def claim_cancellation_resolution(self) -> tuple[bool, Any]:
        """Permit exactly one caller to perform lease/CAS cancellation work."""

        with self._lock:
            if self._cancellation_resolved:
                return False, copy.deepcopy(self._cancellation_resolution)
            if self._cancellation_resolving:
                return False, None
            self._cancellation_resolving = True
            return True, None

    def claim_cancellation_begin(self) -> bool:
        with self._lock:
            if self._cancellation_begin_claimed:
                return False
            self._cancellation_begin_claimed = True
            return True

    def finish_cancellation_begin(self) -> None:
        self._cancellation_begin_complete.set()

    def wait_cancellation_begin(self, timeout: float | None = None) -> bool:
        return self._cancellation_begin_complete.wait(timeout)

    def finish_cancellation_resolution(self, result: Any) -> Any:
        with self._lock:
            if not self._cancellation_resolved:
                self._cancellation_resolution = copy.deepcopy(result)
            self._cancellation_resolved = True
            self._cancellation_resolving = False
            self._maybe_terminal_locked()
            resolved = copy.deepcopy(self._cancellation_resolution)
        self._cancellation_resolution_complete.set()
        return resolved

    def wait_cancellation_resolution(self, timeout: float | None = None) -> bool:
        """Wait until the single cancellation resolver publishes its result."""

        return self._cancellation_resolution_complete.wait(timeout)

    def cancellation_resolution(self) -> Any:
        with self._lock:
            return copy.deepcopy(self._cancellation_resolution)

    def begin_gui_phase(self, phase: str) -> InflightSnapshot:
        with self._lock:
            self._active_gui_phases += 1
            self._phase = str(phase)[:128]
            return self._snapshot_locked()

    def end_gui_phase(self) -> InflightSnapshot:
        with self._lock:
            if self._active_gui_phases > 0:
                self._active_gui_phases -= 1
            self._maybe_terminal_locked()
            return self._snapshot_locked()

    def finish_handler(self, status: str) -> InflightSnapshot:
        with self._lock:
            self._handler_finished = True
            self._terminal_status = str(status)[:64]
            self._maybe_terminal_locked()
            return self._snapshot_locked()

    def _maybe_terminal_locked(self) -> None:
        if self._handler_finished and self._active_gui_phases == 0:
            if self._cancellation_requested and not self._cancellation_resolved:
                return
            self._accepting_cancellation = False
            self._terminal = True
            if self._cancellation_requested:
                self._terminal_status = "cancelled"
            self._phase = "terminal"
