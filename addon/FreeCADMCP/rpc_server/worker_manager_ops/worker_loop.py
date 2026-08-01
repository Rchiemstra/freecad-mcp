"""Background worker queue loop."""

from __future__ import annotations

import queue
import shutil

from ..telemetry import emit as emit_telemetry
from .lifecycle_codes import build_worker_error


def worker_loop(manager) -> None:
    while True:
        try:
            invocation = manager._work_queue.get(timeout=0.2)
        except queue.Empty:
            if manager._stopping:
                return
            continue
        try:
            if invocation.cancelled:
                if invocation.result is None:
                    invocation.result = build_worker_error(
                        "worker_cancelled",
                        "Worker job was cancelled",
                        job_id=invocation.job_id,
                    )
                shutil.rmtree(invocation.workspace, ignore_errors=True)
            elif manager._stopping:
                invocation.result = build_worker_error(
                    "server_stopping",
                    "Worker manager is stopping",
                    job_id=invocation.job_id,
                )
                shutil.rmtree(invocation.workspace, ignore_errors=True)
            else:
                with manager._state_lock:
                    manager._active_invocation = invocation
                emit_telemetry(
                    "worker_manager",
                    "worker_job_started",
                    worker_job_id=invocation.job_id,
                )
                invocation.result = manager._execute_now(invocation)
        finally:
            with manager._state_lock:
                manager._invocations.pop(invocation.job_id, None)
                if manager._active_invocation is invocation:
                    manager._active_invocation = None
            invocation.completed.set()
            manager._admission.release()
            manager._work_queue.task_done()
            result = invocation.result or {}
            emit_telemetry(
                "worker_manager",
                (
                    "worker_job_cancelled"
                    if result.get("error_code") == "WORKER_CANCELLED"
                    else "worker_job_completed"
                ),
                status=(
                    "succeeded"
                    if result.get("success")
                    else (
                        "cancelled"
                        if result.get("error_code") == "WORKER_CANCELLED"
                        else "failed"
                    )
                ),
                error_code=result.get("error_code"),
                worker_job_id=invocation.job_id,
                payload={
                    "execution": result.get("execution"),
                    "legacy_error_code": result.get("legacy_error_code"),
                },
            )
