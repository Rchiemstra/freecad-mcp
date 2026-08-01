"""Helpers extracted from :meth:`GuiDispatcher.submit` for C901 compliance."""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..telemetry import emit as emit_telemetry
from .gui_busy_after_timeout import GuiBusyAfterTimeout
from .gui_dispatch_error import GuiDispatchError
from .gui_dispatch_timeout import GuiDispatchTimeout
from .gui_outcome import GuiOutcome
from .gui_request import GuiRequest
from .gui_task_error import GuiTaskError

if TYPE_CHECKING:
    from .gui_dispatcher_impl import GuiDispatcher


def build_gui_request(
    callable_: Callable[[], Any],
    *,
    request_id: str | None,
    session_id: str | None,
    on_complete: Callable[[str, GuiOutcome], None] | None,
) -> GuiRequest:
    return GuiRequest(
        callable_,
        request_id=request_id or str(uuid.uuid4()),
        session_id=session_id,
        on_complete=on_complete,
    )


def emit_gui_queued_telemetry(request: GuiRequest, timeout: float | None) -> None:
    emit_telemetry(
        "gui_dispatcher",
        "gui_execution_queued",
        request_id=request.request_id,
        execution_id=request.request_id,
        session_id=request.session_id,
        payload={"timeout_seconds": timeout},
    )


def execute_request(request: GuiRequest) -> GuiOutcome:
    """Shared callable/exception path for queued and self-dispatched work."""
    try:
        return GuiOutcome(True, value=request.callable())
    except Exception as exc:
        return GuiOutcome(
            False,
            error=f"RPC task raised {type(exc).__name__}: {exc}",
        )


def unwrap_outcome(outcome: GuiOutcome, request: GuiRequest | None = None) -> Any:
    if outcome.ok:
        return outcome.value
    raise GuiTaskError(
        outcome.error or "Unknown GUI task error",
        request_id=request.request_id if request is not None else None,
        timeout_stage="gui_execution",
        execution_started=True,
    )


def execute_on_gui_thread(dispatcher: GuiDispatcher, request: GuiRequest) -> Any:
    outcome = execute_request(request)
    request.complete(outcome)
    return unwrap_outcome(outcome, request)


def enqueue_gui_request(dispatcher: GuiDispatcher, request: GuiRequest) -> bool:
    """Queue *request* and return whether the wake signal should be emitted."""
    with dispatcher._queue_lock:
        if not dispatcher._accepting:
            raise GuiDispatchError(
                "RPC GUI dispatcher is stopping",
                request_id=request.request_id,
            )
        timed_out = dispatcher._timed_out_request
        if timed_out is not None and timed_out.completed:
            dispatcher._timed_out_request = None
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
            existing = dispatcher._requests_by_owner.get(key)
            if existing is not None and existing.state_snapshot in {
                "completed",
                "cancelled",
            }:
                dispatcher._requests_by_owner.pop(key, None)
                existing = None
            if existing is not None:
                raise GuiDispatchError(
                    "authenticated request already has queued GUI work",
                    request_id=request.request_id,
                )
            dispatcher._requests_by_owner[key] = request
        dispatcher._requests.append(request)
        should_emit = not dispatcher._signal_pending
        if should_emit:
            dispatcher._signal_pending = True
    return should_emit


def wait_for_request_completion(request: GuiRequest, timeout: float | None) -> bool:
    if timeout is None:
        request.completion.wait()
        return True
    return bool(request.completion.wait(timeout))


def forget_cancelled_request(dispatcher: GuiDispatcher, request: GuiRequest) -> None:
    with dispatcher._queue_lock:
        with contextlib.suppress(ValueError):
            dispatcher._requests.remove(request)
        dispatcher._forget_request_locked(request)


def cancel_pending_after_timeout(dispatcher: GuiDispatcher, request: GuiRequest) -> bool:
    return request.cancel_if_pending(lambda: forget_cancelled_request(dispatcher, request))


def quarantine_running_timeout(dispatcher: GuiDispatcher, request: GuiRequest) -> None:
    with dispatcher._queue_lock:
        dispatcher._timed_out_request = request
        pending = list(dispatcher._requests)
        dispatcher._requests.clear()

    for pending_request in pending:
        def forget_pending(
            item: GuiRequest = pending_request,
            disp: GuiDispatcher = dispatcher,
        ) -> None:
            with disp._queue_lock:
                disp._forget_request_locked(item)

        pending_request.cancel_if_pending(forget_pending)


def wait_for_race_winner(request: GuiRequest) -> Any:
    request.completion.wait()
    return unwrap_outcome(
        request.outcome or GuiOutcome(False, error="Missing GUI outcome"),
        request,
    )


def raise_submit_timeout_error(
    request: GuiRequest,
    timeout: float,
    *,
    before_execution: bool,
) -> None:
    suffix = (
        " before execution"
        if before_execution
        else (
            " while executing; execution continues in FreeCAD and may "
            "keep the GUI unresponsive. New GUI work is rejected until "
            "the request finishes"
        )
    )
    error = GuiDispatchTimeout(
        f"Timed out after {timeout}s waiting for FreeCAD GUI response{suffix}",
        request_id=request.request_id,
        timeout_stage="before_execution" if before_execution else "during_execution",
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


def handle_submit_timeout(
    dispatcher: GuiDispatcher,
    request: GuiRequest,
    timeout: float,
) -> Any:
    pending_cancelled = cancel_pending_after_timeout(dispatcher, request)
    if pending_cancelled:
        raise_submit_timeout_error(request, timeout, before_execution=True)
    if request.mark_timed_out_if_running():
        quarantine_running_timeout(dispatcher, request)
        raise_submit_timeout_error(request, timeout, before_execution=False)
    return wait_for_race_winner(request)


def finalize_completed_request(request: GuiRequest) -> Any:
    return unwrap_outcome(
        request.outcome or GuiOutcome(False, error="Missing GUI outcome"),
        request,
    )
