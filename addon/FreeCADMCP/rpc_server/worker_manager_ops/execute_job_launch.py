"""Launch worker subprocess and wait for completion."""

from __future__ import annotations

import contextlib
import subprocess
import threading

from ..process_control import popen_platform_options
from .console import console_message
from .execute_job_helpers import assign_windows_job_object, wait_for_worker_process
from .process_log import drain_process_log
from .worker_invocation import WorkerInvocation


def launch_and_wait_for_worker(
    manager,
    invocation: WorkerInvocation,
    *,
    command: list[str],
    workspace,
    timeout: float,
    started: float,
    log_path,
) -> tuple[int | None, subprocess.Popen | None, object | None, dict | None]:
    job_id = invocation.job_id
    snapshot = invocation.snapshot
    with contextlib.suppress(Exception):
        console_message(
            f"FreeCADMCP: worker ACTIVE job={job_id} "
            f"(timeout={timeout:g}s, snapshot={snapshot.get('primary_document')})"
        )
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(workspace),
            env=manager._worker_environment(workspace),
            **popen_platform_options(),
        )
        manager._active_process = process
        manager._active_job_id = job_id
        log_thread = threading.Thread(
            target=drain_process_log,
            args=(process, log),
            name=f"FreeCADMCP-WorkerLog-{job_id}",
            daemon=True,
        )
        log_thread.start()
        job_object = assign_windows_job_object(process)
        return_code, early_error = wait_for_worker_process(
            manager,
            process,
            job_object,
            log_thread,
            job_id=job_id,
            timeout=timeout,
            started=started,
        )
        return return_code, process, job_object, early_error
