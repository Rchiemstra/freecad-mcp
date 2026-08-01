"""Run a callable on the GUI thread and return its result."""

from __future__ import annotations

import queue
import time
import traceback
from collections.abc import Callable
from typing import Any

import FreeCAD

from . import queue_state
from .wake_signal import WakeSignal


def dispatch_to_gui(task: Callable[[], Any], timeout: float = 60) -> Any:
    """Run ``task`` on the GUI thread and return its result.

    Uses a per-call response queue so a timeout in one call never corrupts
    the response for a subsequent call. Wakes the GUI thread immediately via
    a Qt signal instead of waiting for the next 500 ms heartbeat.

    Returns the task's return value on success, an error string if the task
    raises, or ``{"success": False, "error": ...}`` on timeout.
    """
    response_queue: queue.Queue[Any] = queue.Queue(maxsize=1)

    def _wrapped() -> None:
        try:
            res = task()
        except Exception as exc:
            FreeCAD.Console.PrintError(
                f"MCP RPC: GUI task raised {type(exc).__name__}: {exc}\n"
                f"{traceback.format_exc()}"
            )
            res = f"{type(exc).__name__}: {exc}"
        response_queue.put(res)

    queue_state.rpc_request_queue.put(_wrapped)
    waker = queue_state.waker
    if isinstance(waker, WakeSignal):
        waker.wake()

    try:
        return response_queue.get(timeout=timeout)
    except queue.Empty:
        if queue_state.processing:
            busy_for = time.monotonic() - queue_state.processing_since
            hint = (
                f" (GUI thread has been busy for {busy_for:.1f}s — "
                "consider execute_code_async for heavy OCCT operations)"
            )
        else:
            hint = ""
        return {
            "success": False,
            "error": f"GUI dispatch timed out after {timeout}s{hint}",
        }
