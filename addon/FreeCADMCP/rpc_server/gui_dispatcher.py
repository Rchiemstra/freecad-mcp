"""Event-driven, per-request dispatch onto FreeCAD's Qt GUI thread."""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from PySide import QtCore


class GuiDispatchError(RuntimeError):
    """Base error raised to the XML-RPC handler by GUI dispatch."""


class GuiDispatchTimeout(GuiDispatchError):
    """The GUI did not complete a request before its caller timed out."""


class GuiTaskError(GuiDispatchError):
    """A callable raised while executing on the GUI thread."""


@dataclass(frozen=True)
class GuiOutcome:
    ok: bool
    value: Any = None
    error: str | None = None


@dataclass
class GuiRequest:
    callable: Callable[[], Any]
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
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

    def cancel_if_pending(self) -> bool:
        with self._state_lock:
            if self.state != "pending":
                return False
            self.state = "cancelled"
            self.outcome = GuiOutcome(False, error="GUI request cancelled before execution")
            self.completion.set()
            return True

    def complete(self, outcome: GuiOutcome) -> None:
        with self._state_lock:
            self.outcome = outcome
            self.state = "completed"
            self.completion.set()


class GuiDispatcher(QtCore.QObject):
    """Wake the GUI thread on demand and complete each request independently."""

    wake_requested = QtCore.Signal()

    def __init__(self, parent: QtCore.QObject | None = None):
        super().__init__(parent)
        self._requests: deque[GuiRequest] = deque()
        self._queue_lock = threading.Lock()
        self._signal_pending = False
        self._accepting = True
        try:
            queued = QtCore.Qt.ConnectionType.QueuedConnection
        except AttributeError:
            queued = QtCore.Qt.QueuedConnection
        self.wake_requested.connect(self._drain_one, queued)

    @staticmethod
    def _execute_request(request: GuiRequest) -> GuiOutcome:
        """Shared callable/exception path for queued and self-dispatched work."""
        try:
            return GuiOutcome(True, value=request.callable())
        except Exception as exc:
            return GuiOutcome(
                False,
                error=f"RPC task raised {type(exc).__name__}: {exc}",
            )

    @staticmethod
    def _unwrap(outcome: GuiOutcome) -> Any:
        if outcome.ok:
            return outcome.value
        raise GuiTaskError(outcome.error or "Unknown GUI task error")

    def submit(self, callable_: Callable[[], Any], timeout: float | None) -> Any:
        request = GuiRequest(callable_)

        # start_rpc_server and some trusted internal callers already run on the
        # GUI thread. Waiting on our own event loop here would deadlock.
        if QtCore.QThread.currentThread() == self.thread():
            outcome = self._execute_request(request)
            request.complete(outcome)
            return self._unwrap(outcome)

        with self._queue_lock:
            if not self._accepting:
                raise GuiDispatchError("RPC GUI dispatcher is stopping")
            self._requests.append(request)
            should_emit = not self._signal_pending
            if should_emit:
                self._signal_pending = True

        if should_emit:
            self.wake_requested.emit()

        if timeout is None:
            request.completion.wait()
            completed = True
        else:
            completed = request.completion.wait(timeout)
        if not completed:
            pending_cancelled = request.cancel_if_pending()
            suffix = " before execution" if pending_cancelled else " while executing"
            raise GuiDispatchTimeout(
                f"Timed out after {timeout}s waiting for FreeCAD GUI response{suffix}"
            )
        return self._unwrap(request.outcome or GuiOutcome(False, error="Missing GUI outcome"))

    @QtCore.Slot()
    def _drain_one(self) -> None:
        with self._queue_lock:
            if not self._requests:
                self._signal_pending = False
                return
            request = self._requests.popleft()

        if request.mark_running():
            request.complete(self._execute_request(request))

        # Exactly one bounded unit of work is performed per queued callback.
        with self._queue_lock:
            has_more = bool(self._requests)
            if not has_more:
                self._signal_pending = False
        if has_more:
            self.wake_requested.emit()

    def stop_accepting(self) -> None:
        with self._queue_lock:
            self._accepting = False
            pending = list(self._requests)
            self._requests.clear()
            self._signal_pending = False
        for request in pending:
            request.cancel_if_pending()

    @property
    def pending_count(self) -> int:
        with self._queue_lock:
            return len(self._requests)
