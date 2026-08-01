"""Event-driven, per-request dispatch onto FreeCAD's Qt GUI thread."""

from __future__ import annotations

import contextlib
import threading
from collections import deque
from collections.abc import Callable
from typing import Any

from PySide import QtCore

from ..telemetry import emit as emit_telemetry
from .gui_outcome import GuiOutcome
from .gui_request import GuiRequest
from .navigation_guards import gui_busy_for_3d_navigation
from .submit_helpers import (
    build_gui_request,
    emit_gui_queued_telemetry,
    enqueue_gui_request,
    execute_on_gui_thread,
    execute_request,
    finalize_completed_request,
    handle_submit_timeout,
    wait_for_request_completion,
)


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

    def submit(
        self,
        callable_: Callable[[], Any],
        timeout: float | None,
        *,
        request_id: str | None = None,
        session_id: str | None = None,
        on_complete: Callable[[str, GuiOutcome], None] | None = None,
    ) -> Any:
        request = build_gui_request(
            callable_,
            request_id=request_id,
            session_id=session_id,
            on_complete=on_complete,
        )
        emit_gui_queued_telemetry(request, timeout)

        # start_rpc_server and some trusted internal callers already run on the
        # GUI thread. Waiting on our own event loop here would deadlock.
        if QtCore.QThread.currentThread() == self.thread():
            return execute_on_gui_thread(self, request)

        should_emit = enqueue_gui_request(self, request)
        if should_emit:
            self.wake_requested.emit()

        if not wait_for_request_completion(request, timeout):
            return handle_submit_timeout(self, request, timeout)
        return finalize_completed_request(request)

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
                with contextlib.suppress(ValueError):
                    self._requests.remove(request)
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
        if gui_busy_for_3d_navigation():
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
                execute_request(request),
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
            def forget_stopped(item: GuiRequest = request) -> None:
                with self._queue_lock:
                    self._forget_request_locked(item)

            request.cancel_if_pending(forget_stopped)

    @property
    def pending_count(self) -> int:
        with self._queue_lock:
            return len(self._requests)
