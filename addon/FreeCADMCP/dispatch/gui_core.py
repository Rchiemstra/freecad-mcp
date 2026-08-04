"""Standard-library GUI dispatch state machine.

Thread ownership and event-loop operations are supplied by a composition
adapter.  Keeping those callbacks at the boundary lets this module remain
importable without FreeCAD or Qt.
"""

from __future__ import annotations

import contextlib
import threading
import uuid
from collections import deque
from collections.abc import Callable
from typing import Any

from .gui_errors import (
    GuiBusyAfterTimeout,
    GuiDispatchError,
    GuiDispatchTimeout,
    GuiTaskError,
)
from .gui_outcome import GuiOutcome
from .gui_request import GuiRequest, TelemetryCallback


class GuiDispatchCore:
    """Queue work for exactly one injected GUI owner thread."""

    def __init__(
        self,
        *,
        is_gui_thread: Callable[[], bool],
        wake_gui: Callable[[], None],
        schedule_wake: Callable[[int, Callable[[], None]], None],
        gui_busy: Callable[[], bool],
        emit_telemetry: TelemetryCallback,
    ) -> None:
        self._is_gui_thread = is_gui_thread
        self._wake_gui = wake_gui
        self._schedule_wake = schedule_wake
        self._gui_busy = gui_busy
        self._emit_telemetry = emit_telemetry
        self._requests: deque[GuiRequest] = deque()
        # Cancellation and completion callbacks can synchronously re-enter the
        # dispatcher; an RLock keeps cleanup atomic without deadlocking them.
        self._queue_lock = threading.RLock()
        self._signal_pending = False
        self._accepting = True
        self._timed_out_request: GuiRequest | None = None
        self._requests_by_owner: dict[tuple[str, str], GuiRequest] = {}

    def _emit(self, event: str, **fields: Any) -> None:
        with contextlib.suppress(Exception):
            self._emit_telemetry("gui_dispatcher", event, **fields)

    @staticmethod
    def _execute_request(request: GuiRequest) -> GuiOutcome:
        try:
            return GuiOutcome(True, value=request.callable())
        except Exception as exc:
            # Preserve the legacy distinction between task failures and
            # process-control exceptions.
            return GuiOutcome(
                False,
                error=f"RPC task raised {type(exc).__name__}: {exc}",
            )

    @staticmethod
    def _unwrap(request: GuiRequest) -> Any:
        outcome = request.outcome or GuiOutcome(False, error="Missing GUI outcome")
        if outcome.ok:
            return outcome.value
        raise GuiTaskError(
            outcome.error or "Unknown GUI task error",
            request_id=request.request_id,
            timeout_stage="gui_execution",
            execution_started=True,
        )

    def _new_request(
        self,
        callable_: Callable[[], Any],
        *,
        request_id: str | None,
        session_id: str | None,
        on_complete: Callable[[str, GuiOutcome], None] | None,
    ) -> GuiRequest:
        request = GuiRequest(
            callable_,
            request_id=request_id or str(uuid.uuid4()),
            session_id=session_id,
            on_complete=on_complete,
        )
        request._emit_telemetry = self._emit_telemetry
        return request

    def submit(
        self,
        callable_: Callable[[], Any],
        timeout: float | None,
        *,
        request_id: str | None = None,
        session_id: str | None = None,
        on_complete: Callable[[str, GuiOutcome], None] | None = None,
    ) -> Any:
        request = self._new_request(
            callable_,
            request_id=request_id,
            session_id=session_id,
            on_complete=on_complete,
        )
        self._emit(
            "gui_execution_queued",
            request_id=request.request_id,
            execution_id=request.request_id,
            session_id=request.session_id,
            payload={"timeout_seconds": timeout},
        )

        try:
            on_owner = bool(self._is_gui_thread())
        except Exception as exc:
            raise GuiDispatchError(
                f"Could not determine GUI thread ownership: {exc}",
                request_id=request.request_id,
            ) from exc
        if on_owner:
            with self._queue_lock:
                if not self._accepting:
                    raise GuiDispatchError(
                        "RPC GUI dispatcher is stopping",
                        request_id=request.request_id,
                    )
            request.complete(self._execute_request(request))
            return self._unwrap(request)

        should_wake = self._enqueue(request)
        if should_wake and not self._request_wake():
            raise GuiDispatchError(
                "Could not wake the GUI dispatcher",
                request_id=request.request_id,
            )

        if timeout is None:
            request.completion.wait()
        elif not request.completion.wait(timeout):
            return self._handle_timeout(request, float(timeout))
        return self._unwrap(request)

    def _enqueue(self, request: GuiRequest) -> bool:
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
            should_wake = not self._signal_pending
            if should_wake:
                self._signal_pending = True
            return should_wake

    def _forget_locked(self, request: GuiRequest) -> None:
        if request.session_id:
            key = (request.session_id, request.request_id)
            if self._requests_by_owner.get(key) is request:
                self._requests_by_owner.pop(key, None)

    def _cancel_requests(self, requests: list[GuiRequest]) -> None:
        for request in requests:
            request.cancel_if_pending()

    def _fail_pending_wakes(self) -> None:
        with self._queue_lock:
            pending = list(self._requests)
            self._requests.clear()
            self._signal_pending = False
            for request in pending:
                self._forget_locked(request)
        self._cancel_requests(pending)

    def _request_wake(self) -> bool:
        try:
            self._wake_gui()
            return True
        except Exception:
            self._fail_pending_wakes()
            return False

    def _scheduled_wake(self) -> None:
        self._request_wake()

    def _schedule_deferred_wake(self) -> bool:
        try:
            self._schedule_wake(50, self._scheduled_wake)
            return True
        except Exception:
            self._fail_pending_wakes()
            return False

    def _remove_pending(self, request: GuiRequest) -> None:
        with self._queue_lock:
            with contextlib.suppress(ValueError):
                self._requests.remove(request)
            self._forget_locked(request)
            if not self._requests:
                self._signal_pending = False

    def _quarantine_running(self, request: GuiRequest) -> None:
        with self._queue_lock:
            self._timed_out_request = request
            pending = list(self._requests)
            self._requests.clear()
            for item in pending:
                self._forget_locked(item)
        self._cancel_requests(pending)

    def _raise_timeout(
        self,
        request: GuiRequest,
        timeout: float,
        *,
        before_execution: bool,
    ) -> None:
        suffix = (
            " before execution"
            if before_execution
            else (
                " while executing; execution continues in FreeCAD and may keep "
                "the GUI unresponsive. New GUI work is rejected until the "
                "request finishes"
            )
        )
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
        self._emit(
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

    def _handle_timeout(self, request: GuiRequest, timeout: float) -> Any:
        if request.cancel_if_pending(lambda: self._remove_pending(request)):
            self._raise_timeout(request, timeout, before_execution=True)
        if request.mark_timed_out_if_running():
            self._quarantine_running(request)
            self._raise_timeout(request, timeout, before_execution=False)
        # Completion won the race after Event.wait returned false.
        request.completion.wait()
        return self._unwrap(request)

    def cancel_request(self, session_id: str, request_id: str) -> str:
        key = (str(session_id), str(request_id))
        with self._queue_lock:
            request = self._requests_by_owner.get(key)
            if request is None:
                return "not_queued"
            if request.cancel_if_pending(lambda: self._remove_pending(request)):
                return "cancelled_pending"
            state = request.state_snapshot
            if state in {"running", "timed_out_running"}:
                return "running"
            self._forget_locked(request)
            return "completed"

    def _require_owner_thread(self) -> None:
        try:
            on_owner = bool(self._is_gui_thread())
        except Exception as exc:
            raise GuiDispatchError(
                f"Could not determine GUI thread ownership: {exc}"
            ) from exc
        if not on_owner:
            raise GuiDispatchError(
                "GUI dispatch queue may only be drained by its owner thread"
            )

    def _take_next_request(self) -> GuiRequest | None:
        with self._queue_lock:
            if not self._requests:
                self._signal_pending = False
                return None
            return self._requests.popleft()

    def _gui_is_busy(self) -> bool:
        try:
            return bool(self._gui_busy())
        except Exception:
            return False

    def _defer_busy_request(self, request: GuiRequest) -> None:
        should_requeue = False
        with self._queue_lock:
            if request.state_snapshot == "pending" and self._accepting:
                self._requests.appendleft(request)
                self._signal_pending = True
                should_requeue = True
            else:
                self._forget_locked(request)
        if should_requeue:
            self._schedule_deferred_wake()
        else:
            request.cancel_if_pending()

    def _start_request(self, request: GuiRequest) -> bool:
        with self._queue_lock:
            should_run = self._accepting and request.mark_running()
            if not should_run:
                self._forget_locked(request)
        if not should_run:
            request.cancel_if_pending()
        return bool(should_run)

    def _run_request(self, request: GuiRequest) -> None:
        try:
            self._emit(
                "gui_execution_started",
                request_id=request.request_id,
                execution_id=request.request_id,
                session_id=request.session_id,
                payload={},
            )
            try:
                outcome = self._execute_request(request)
            except BaseException as exc:
                request.complete(
                    GuiOutcome(
                        False,
                        error=f"RPC task raised {type(exc).__name__}: {exc}",
                    ),
                    before_wake=lambda: self._forget_after_execution(request),
                )
                raise
            request.complete(
                outcome,
                before_wake=lambda: self._forget_after_execution(request),
            )
        finally:
            with self._queue_lock:
                if self._timed_out_request is request:
                    self._timed_out_request = None
                self._forget_locked(request)
                has_more = bool(self._requests)
                if not has_more:
                    self._signal_pending = False
            if has_more:
                self._request_wake()

    def drain_one(self) -> None:
        self._require_owner_thread()
        request = self._take_next_request()
        if request is None:
            return
        if self._gui_is_busy():
            self._defer_busy_request(request)
            return
        if self._start_request(request):
            self._run_request(request)

    def _forget_after_execution(self, request: GuiRequest) -> None:
        with self._queue_lock:
            self._forget_locked(request)

    def stop_accepting(self) -> None:
        with self._queue_lock:
            self._accepting = False
            pending = list(self._requests)
            self._requests.clear()
            self._signal_pending = False
            for request in pending:
                self._forget_locked(request)
        self._cancel_requests(pending)

    @property
    def pending_count(self) -> int:
        with self._queue_lock:
            return len(self._requests)
