"""Compatibility helpers for submission to :class:`GuiDispatchCore`.

The functions retain the legacy helper signatures while resolving either a
pure core or the narrow Qt adapter that owns one.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Callable
from typing import Any

from .gui_errors import GuiDispatchTimeout, GuiTaskError
from .gui_outcome import GuiOutcome
from .gui_request import GuiRequest


def _dispatch_core(dispatcher: Any) -> Any:
    return getattr(dispatcher, "_core", dispatcher)


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
    """Emit through the request-bound port without locating runtime telemetry.

    The live core binds this callback before emitting. Standalone compatibility
    callers may inject it on ``GuiRequest``; an unbound pure request is inert.
    """

    emitter = request._emit_telemetry
    if emitter is None:
        return
    with contextlib.suppress(Exception):
        emitter(
            "gui_dispatcher",
            "gui_execution_queued",
            request_id=request.request_id,
            execution_id=request.request_id,
            session_id=request.session_id,
            payload={"timeout_seconds": timeout},
        )


def execute_request(request: GuiRequest) -> GuiOutcome:
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


def execute_on_gui_thread(dispatcher: Any, request: GuiRequest) -> Any:
    del dispatcher  # Compatibility parameter; the caller owns thread routing.
    outcome = execute_request(request)
    request.complete(outcome)
    return unwrap_outcome(outcome, request)


def enqueue_gui_request(dispatcher: Any, request: GuiRequest) -> bool:
    core = _dispatch_core(dispatcher)
    if request._emit_telemetry is None:
        request._emit_telemetry = core._emit_telemetry
    return bool(core._enqueue(request))


def wait_for_request_completion(request: GuiRequest, timeout: float | None) -> bool:
    if timeout is None:
        request.completion.wait()
        return True
    return bool(request.completion.wait(timeout))


def forget_cancelled_request(dispatcher: Any, request: GuiRequest) -> None:
    _dispatch_core(dispatcher)._remove_pending(request)


def cancel_pending_after_timeout(dispatcher: Any, request: GuiRequest) -> bool:
    return request.cancel_if_pending(
        lambda: forget_cancelled_request(dispatcher, request)
    )


def quarantine_running_timeout(dispatcher: Any, request: GuiRequest) -> None:
    _dispatch_core(dispatcher)._quarantine_running(request)


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
    emitter = request._emit_telemetry
    if emitter is not None:
        with contextlib.suppress(Exception):
            emitter(
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
    dispatcher: Any,
    request: GuiRequest,
    timeout: float,
) -> Any:
    if cancel_pending_after_timeout(dispatcher, request):
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
