"""Event-driven, per-request dispatch onto FreeCAD's Qt GUI thread."""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from PySide import QtCore, QtWidgets

from .telemetry import emit as emit_telemetry


def _is_unittest_mock(value: Any) -> bool:
    return type(value).__module__.startswith("unittest.mock")


def _mouse_buttons_held(app: Any) -> bool:
    """True only for a real Qt mouse-button bitfield with buttons down."""
    try:
        buttons = app.mouseButtons()
    except Exception:
        return False
    if _is_unittest_mock(buttons):
        return False
    try:
        return int(buttons) != int(QtCore.Qt.NoButton)
    except (TypeError, ValueError):
        return buttons != QtCore.Qt.NoButton


def _blocking_overlay_active(app: Any) -> bool:
    for getter_name in ("activePopupWidget", "activeModalWidget"):
        getter = getattr(app, getter_name, None)
        if getter is None:
            continue
        try:
            widget = getter()
        except Exception:
            continue
        if widget is None or _is_unittest_mock(widget):
            continue
        return True
    return False


def _gui_busy_for_3d_navigation() -> bool:
    """Skip GUI dispatch while the user is interacting with the 3D view / dialogs."""
    app = QtWidgets.QApplication.instance()
    if app is None or _is_unittest_mock(app):
        return False
    try:
        return _mouse_buttons_held(app) or _blocking_overlay_active(app)
    except Exception:
        return False


class GuiDispatchError(RuntimeError):
    """Base error raised to the XML-RPC handler by GUI dispatch."""

    error_code = "GUI_DISPATCH_FAILED"

    def __init__(
        self,
        message: str,
        *,
        request_id: str | None = None,
        timeout_stage: str | None = None,
        execution_started: bool = False,
        mutation_started: bool = False,
        completion_uncertain: bool = False,
    ) -> None:
        self.request_id = request_id
        self.timeout_stage = timeout_stage
        self.execution_started = bool(execution_started)
        self.mutation_started = bool(mutation_started)
        self.completion_uncertain = bool(completion_uncertain)
        super().__init__(message)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "timeout_stage": self.timeout_stage,
            "request_id": self.request_id,
            "execution_started": self.execution_started,
            "mutation_started": self.mutation_started,
            "completion_uncertain": self.completion_uncertain,
        }


class GuiDispatchTimeout(GuiDispatchError):
    """The GUI did not complete a request before its caller timed out."""


class GuiBusyAfterTimeout(GuiDispatchError):
    """A timed-out request is still occupying FreeCAD's GUI thread."""

    error_code = "GUI_BUSY_AFTER_TIMEOUT"


class GuiTaskError(GuiDispatchError):
    """A callable raised while executing on the GUI thread."""

    error_code = "GUI_TASK_FAILED"


@dataclass(frozen=True)
class GuiOutcome:
    ok: bool
    value: Any = None
    error: str | None = None


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
            try:
                callback(self.request_id, outcome)
            except Exception:
                pass
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
            try:
                callback(self.request_id, outcome)
            except Exception:
                # Completion reporting must never destabilize the GUI queue.
                pass
        if before_wake is not None:
            before_wake()
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
        self._timed_out_request: GuiRequest | None = None
        self._requests_by_owner: dict[tuple[str, str], GuiRequest] = {}
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
    def _unwrap(outcome: GuiOutcome, request: GuiRequest | None = None) -> Any:
        if outcome.ok:
            return outcome.value
        raise GuiTaskError(
            outcome.error or "Unknown GUI task error",
            request_id=request.request_id if request is not None else None,
            timeout_stage="gui_execution",
            execution_started=True,
        )

    def submit(
        self,
        callable_: Callable[[], Any],
        timeout: float | None,
        *,
        request_id: str | None = None,
        session_id: str | None = None,
        on_complete: Callable[[str, GuiOutcome], None] | None = None,
    ) -> Any:
        request = GuiRequest(
            callable_,
            request_id=request_id or str(uuid.uuid4()),
            session_id=session_id,
            on_complete=on_complete,
        )
        emit_telemetry(
            "gui_dispatcher",
            "gui_execution_queued",
            request_id=request.request_id,
            execution_id=request.request_id,
            session_id=request.session_id,
            payload={"timeout_seconds": timeout},
        )

        # start_rpc_server and some trusted internal callers already run on the
        # GUI thread. Waiting on our own event loop here would deadlock.
        if QtCore.QThread.currentThread() == self.thread():
            outcome = self._execute_request(request)
            request.complete(outcome)
            return self._unwrap(outcome, request)

        with self._queue_lock:
            if not self._accepting:
                raise GuiDispatchError(
                    "RPC GUI dispatcher is stopping",
                    request_id=request.request_id,
                )
            timed_out = self._timed_out_request
            if timed_out is not None and timed_out.completed:
                self._timed_out_request = None
                timed_out = None
            if timed_out is not None:
                raise GuiBusyAfterTimeout(
                    "FreeCAD GUI is still executing a request that timed out; "
                    "new GUI work is rejected until it finishes",
                    request_id=request.request_id,
                    timeout_stage="admission",
                    completion_uncertain=True,
                )
            if request.session_id:
                key = (request.session_id, request.request_id)
                existing = self._requests_by_owner.get(key)
                if existing is not None and existing.state_snapshot in {
                    "completed",
                    "cancelled",
                }:
                    self._requests_by_owner.pop(key, None)
                    existing = None
                if existing is not None:
                    raise GuiDispatchError(
                        "authenticated request already has queued GUI work",
                        request_id=request.request_id,
                    )
                self._requests_by_owner[key] = request
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
            def forget_cancelled_request() -> None:
                with self._queue_lock:
                    try:
                        self._requests.remove(request)
                    except ValueError:
                        pass
                    self._forget_request_locked(request)

            pending_cancelled = request.cancel_if_pending(forget_cancelled_request)
            if pending_cancelled:
                suffix = " before execution"
            elif request.mark_timed_out_if_running():
                with self._queue_lock:
                    self._timed_out_request = request
                    pending = list(self._requests)
                    self._requests.clear()
                for pending_request in pending:
                    def forget_pending(item=pending_request) -> None:
                        with self._queue_lock:
                            self._forget_request_locked(item)

                    pending_request.cancel_if_pending(forget_pending)
                suffix = (
                    " while executing; execution continues in FreeCAD and may "
                    "keep the GUI unresponsive. New GUI work is rejected until "
                    "the request finishes"
                )
            else:
                # Completion won the race with the timeout. Return its outcome
                # instead of incorrectly quarantining an idle dispatcher.
                request.completion.wait()
                return self._unwrap(
                    request.outcome or GuiOutcome(False, error="Missing GUI outcome"),
                    request,
                )
            before_execution = pending_cancelled
            error = GuiDispatchTimeout(
                f"Timed out after {timeout}s waiting for FreeCAD GUI response{suffix}",
                request_id=request.request_id,
                timeout_stage=(
                    "before_execution" if before_execution else "during_execution"
                ),
                execution_started=not before_execution,
                completion_uncertain=not before_execution,
            )
            error.error_code = (
                "GUI_TIMEOUT_BEFORE_EXECUTION"
                if before_execution
                else "GUI_TIMEOUT_DURING_EXECUTION"
            )
            emit_telemetry(
                "gui_dispatcher",
                "gui_execution_timeout",
                status="timed_out",
                error_code=error.error_code,
                request_id=request.request_id,
                execution_id=request.request_id,
                session_id=request.session_id,
                payload={
                    "timeout_stage": error.timeout_stage,
                    "execution_started": error.execution_started,
                    "completion_uncertain": error.completion_uncertain,
                },
            )
            raise error
        return self._unwrap(
            request.outcome or GuiOutcome(False, error="Missing GUI outcome"),
            request,
        )

    def _forget_request_locked(self, request: GuiRequest) -> None:
        if request.session_id:
            key = (request.session_id, request.request_id)
            if self._requests_by_owner.get(key) is request:
                self._requests_by_owner.pop(key, None)

    def cancel_request(self, session_id: str, request_id: str) -> str:
        """Cancel only GUI work owned by the exact authenticated request key.

        Pending work is removed atomically from the queue.  Running work is
        never claimed to be stopped; its cooperative request token must carry
        cancellation through actual completion.
        """

        key = (str(session_id), str(request_id))
        with self._queue_lock:
            request = self._requests_by_owner.get(key)
            if request is None:
                return "not_queued"
            def forget_pending() -> None:
                try:
                    self._requests.remove(request)
                except ValueError:
                    pass
                self._forget_request_locked(request)

            if request.cancel_if_pending(forget_pending):
                if not self._requests:
                    self._signal_pending = False
                return "cancelled_pending"
            state = request.state_snapshot
            if state in {"running", "timed_out_running"}:
                return "running"
            self._forget_request_locked(request)
            return "completed"

    @QtCore.Slot()
    def _drain_one(self) -> None:
        with self._queue_lock:
            if not self._requests:
                self._signal_pending = False
                return
            request = self._requests.popleft()

        # Do not mutate the document/viewer while the user is mid-drag in the
        # 3D view. The legacy gui_dispatch path had this guard; without it,
        # RPC work (recompute/selection/updateGui) races Coin navigation and
        # surfaces as AccessViolation / lost live redraw on every mouse move.
        if _gui_busy_for_3d_navigation():
            with self._queue_lock:
                self._requests.appendleft(request)
                self._signal_pending = True
            QtCore.QTimer.singleShot(50, self.wake_requested.emit)
            return

        if request.mark_running():
            emit_telemetry(
                "gui_dispatcher",
                "gui_execution_started",
                request_id=request.request_id,
                execution_id=request.request_id,
                session_id=request.session_id,
                payload={},
            )
            def forget_before_wake() -> None:
                with self._queue_lock:
                    self._forget_request_locked(request)

            request.complete(
                self._execute_request(request),
                before_wake=forget_before_wake,
            )

        # Exactly one bounded unit of work is performed per queued callback.
        with self._queue_lock:
            if self._timed_out_request is request:
                self._timed_out_request = None
            self._forget_request_locked(request)
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
            def forget_stopped(item=request) -> None:
                with self._queue_lock:
                    self._forget_request_locked(item)

            request.cancel_if_pending(forget_stopped)

    @property
    def pending_count(self) -> int:
        with self._queue_lock:
            return len(self._requests)
