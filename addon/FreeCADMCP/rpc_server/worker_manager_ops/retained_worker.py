"""Own a worker process until it exits, not merely until its job result is ready.

A timeout, quota kill, or cancel reports the job error as soon as termination
gives up. That report is not the process exiting. Dropping the handle here
freed the admission slot, deleted the workspace the process was still writing,
and let stop() release the artifact-root lock while the process remained alive.
"""

from __future__ import annotations

import shutil
import time
from typing import Any

from ..process_control import terminate_process_tree
from .artifact_roots import release_artifact_root


def process_still_running(process: Any) -> bool:
    return process is not None and process.poll() is None


def request_process_termination(manager: Any, process: Any, grace: float = 2.0) -> bool:
    """Terminate one tracked process. A process that has already exited is done."""

    if process is None:
        return True
    with manager._terminate_lock:
        if process.poll() is not None:
            return True
        return terminate_process_tree(process, manager._retained_job_object, grace=grace)


def finish_job_process(manager: Any, workspace: Any, job_object: Any) -> None:
    """Keep a still-running process. Reap a process that has actually exited."""

    with manager._terminate_lock:
        process = manager._active_process
        if process_still_running(process):
            manager._retained_workspace = workspace
            if job_object is not None:
                manager._retained_job_object = job_object
            return
        closing = job_object if job_object is not None else manager._retained_job_object
        manager._retained_job_object = None
        if closing is not None:
            closing.close()
    with manager._state_lock:
        manager._active_process = None
        manager._active_job_id = None
        manager._retained_workspace = None
    shutil.rmtree(workspace, ignore_errors=True)


def reap_retained_worker(manager: Any, invocation: Any) -> None:
    """Block the active slot until the retained process exits, then delete its workspace."""

    process = manager._active_process
    workspace = manager._retained_workspace
    if process is not None:
        next_try = 0.0
        while process.poll() is None:
            now = time.monotonic()
            if now >= next_try:
                request_process_termination(manager, process, grace=0.2)
                next_try = now + 1.0
            if process.poll() is None:
                time.sleep(manager.monitor_interval_seconds)
    _drop_tracked_process(manager, invocation, workspace)


def release_artifact_root_once(manager: Any) -> None:
    """Release this manager's artifact root after its last worker has exited."""

    with manager._state_lock:
        if manager._artifact_released:
            return
        if process_still_running(manager._active_process):
            return
        manager._artifact_released = True
        owner = manager._artifact_owner
    release_artifact_root(owner)


def clear_invocation(manager: Any, invocation: Any) -> None:
    manager._invocations.pop(invocation.job_id, None)
    if manager._active_invocation is invocation:
        manager._active_invocation = None


def _drop_tracked_process(manager: Any, invocation: Any, workspace: Any) -> None:
    with manager._terminate_lock:
        closing = manager._retained_job_object
        manager._retained_job_object = None
        if closing is not None:
            closing.close()
    with manager._state_lock:
        manager._active_process = None
        manager._active_job_id = None
        manager._retained_workspace = None
        clear_invocation(manager, invocation)
    if workspace is not None:
        shutil.rmtree(workspace, ignore_errors=True)
