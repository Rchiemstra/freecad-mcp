"""Background worker queue loop."""

from __future__ import annotations

import queue
import shutil

from ..telemetry import emit as emit_telemetry
from .lifecycle_codes import build_worker_error
from .retained_worker import (
    clear_invocation,
    process_still_running,
    reap_retained_worker,
    release_artifact_root_once,
)


def worker_loop(manager) -> None:
    while True:
        invocation = _next_invocation(manager)
        if invocation is None:
            return
        _run_invocation(manager, invocation)


def _next_invocation(manager):
    while True:
        try:
            return manager._work_queue.get(timeout=0.2)
        except queue.Empty:
            if manager._stopping and not process_still_running(manager._active_process):
                release_artifact_root_once(manager)
                return None


def _run_invocation(manager, invocation) -> None:
    try:
        if invocation.cancelled:
            _reject_invocation(invocation, "worker_cancelled", "Worker job was cancelled")
        elif manager._stopping:
            _reject_invocation(invocation, "server_stopping", "Worker manager is stopping")
        else:
            _execute_active(manager, invocation)
    finally:
        _settle_invocation(manager, invocation)


def _reject_invocation(invocation, error_code: str, message: str) -> None:
    if invocation.result is None:
        invocation.result = build_worker_error(
            error_code,
            message,
            job_id=invocation.job_id,
        )
    shutil.rmtree(invocation.workspace, ignore_errors=True)


def _execute_active(manager, invocation) -> None:
    with manager._state_lock:
        manager._active_invocation = invocation
        manager._last_error = None
    emit_telemetry(
        "worker_manager",
        "worker_job_started",
        worker_job_id=invocation.job_id,
    )
    try:
        invocation.result = manager._execute_now(invocation)
    except Exception as exc:
        if invocation.result is None:
            invocation.result = build_worker_error(
                "worker_unavailable",
                str(exc),
                job_id=invocation.job_id,
            )


def _settle_invocation(manager, invocation) -> None:
    with manager._state_lock:
        if invocation.result and not invocation.result.get("success"):
            manager._last_error = str(invocation.result.get("error") or "Worker job failed")
    alive = process_still_running(manager._active_process)
    if alive:
        # The job result is ready. The process still occupies the slot.
        invocation.completed.set()
        _emit_finished(invocation)
        try:
            reap_retained_worker(manager, invocation)
        finally:
            if not process_still_running(manager._active_process):
                manager._admission.release()
            manager._work_queue.task_done()
        return
    if manager._retained_workspace is not None:
        reap_retained_worker(manager, invocation)
    else:
        with manager._state_lock:
            clear_invocation(manager, invocation)
    invocation.completed.set()
    manager._admission.release()
    manager._work_queue.task_done()
    _emit_finished(invocation)


def _emit_finished(invocation) -> None:
    result = invocation.result or {}
    cancelled = result.get("error_code") == "WORKER_CANCELLED"
    emit_telemetry(
        "worker_manager",
        "worker_job_cancelled" if cancelled else "worker_job_completed",
        status=(
            "succeeded"
            if result.get("success")
            else "cancelled"
            if cancelled
            else "failed"
        ),
        error_code=result.get("error_code"),
        worker_job_id=invocation.job_id,
        payload={
            "execution": result.get("execution"),
            "legacy_error_code": result.get("legacy_error_code"),
        },
    )
