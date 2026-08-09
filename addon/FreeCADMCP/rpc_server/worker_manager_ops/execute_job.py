"""Run one isolated worker job synchronously."""

from __future__ import annotations

import shutil
import time

from ..snapshot_service_ops.materialize_aliases import materialize_load_aliases
from ..worker_protocol import (
    ProtocolError,
    UnsupportedWorkerGuiError,
    clamp_timeout,
    validate_job,
    write_json_atomic,
)
from .executable_discovery import discover_executable
from .execute_job_helpers import (
    build_worker_failure_payload,
    build_worker_success_payload,
    load_worker_result,
)
from .execute_job_launch import launch_and_wait_for_worker
from .lifecycle_codes import build_worker_error
from .temp_usage import temp_usage
from .worker_invocation import WorkerInvocation
from .worker_version_mismatch import WorkerVersionMismatch


def _prepare_worker_job(manager, invocation: WorkerInvocation, timeout: float):
    snapshot = invocation.snapshot
    workspace = invocation.workspace
    job_id = invocation.job_id
    materialize_load_aliases(snapshot)
    executable = discover_executable(manager)
    result_path = workspace / "result.json"
    job_path = workspace / "job.json"
    artifact_directory = workspace / "artifacts"
    artifact_directory.mkdir(parents=True, exist_ok=True)
    job = {
        "schema_version": 1,
        "job_id": job_id,
        "kind": "execute_code",
        "result_path": str(result_path),
        "snapshot": snapshot,
        "code": invocation.code,
        "options": {**invocation.options, "timeout_seconds": timeout},
        "artifact_directory": str(artifact_directory),
    }
    validate_job(job)
    write_json_atomic(job_path, job)
    command = [
        str(executable),
        str(manager.module_dir / "worker_entry.py"),
        "--pass",
        str(job_path),
    ]
    return result_path, artifact_directory, command


def _preflight_worker_job(manager, invocation: WorkerInvocation) -> dict | None:
    job_id = invocation.job_id
    if invocation.cancelled:
        return build_worker_error(
            "worker_cancelled", "Worker job was cancelled", job_id=job_id
        )
    if manager._stopping:
        return build_worker_error("server_stopping", "Worker manager is stopping")
    if temp_usage(manager.temp_root) > manager.temp_root_limit_bytes:
        return build_worker_error(
            "resource_limit_exceeded",
            "Managed temporary root exceeds its configured limit after snapshot aliases",
            job_id=job_id,
        )
    return None


def _finalize_worker_result(
    manager,
    invocation: WorkerInvocation,
    *,
    return_code: int,
    result: dict,
    started: float,
    artifact_directory,
) -> dict:
    job_id = invocation.job_id
    if result.get("status") == "ok" and return_code == 0:
        try:
            return build_worker_success_payload(
                manager,
                invocation,
                result,
                return_code=return_code,
                started=started,
                artifact_directory=artifact_directory,
            )
        except Exception as exc:
            return build_worker_error("resource_limit_exceeded", str(exc), job_id=job_id)
    return build_worker_failure_payload(
        invocation, result, return_code=return_code, started=started
    )


def _run_worker_job(
    manager,
    invocation: WorkerInvocation,
    *,
    timeout: float,
    started: float,
) -> tuple[dict, object | None]:
    job_id = invocation.job_id
    workspace = invocation.workspace
    result_path, artifact_directory, command = _prepare_worker_job(
        manager, invocation, timeout
    )
    if invocation.cancelled:
        return (
            build_worker_error(
                "worker_cancelled", "Worker job was cancelled", job_id=job_id
            ),
            None,
        )
    return_code, _process, job_object, early_error = launch_and_wait_for_worker(
        manager,
        invocation,
        command=command,
        workspace=workspace,
        timeout=timeout,
        started=started,
        log_path=workspace / "worker.log",
    )
    if early_error is not None:
        return early_error, job_object
    result, load_error = load_worker_result(
        invocation, result_path, return_code=return_code, snapshot=invocation.snapshot
    )
    if load_error is not None:
        return load_error, job_object
    assert result is not None
    return (
        _finalize_worker_result(
            manager,
            invocation,
            return_code=return_code,
            result=result,
            started=started,
            artifact_directory=artifact_directory,
        ),
        job_object,
    )


def execute_job_now(manager, invocation: WorkerInvocation) -> dict:
    job_id = invocation.job_id
    workspace = invocation.workspace
    timeout = clamp_timeout(invocation.options.get("timeout_seconds"))
    job_object = None
    started = time.monotonic()
    try:
        preflight_error = _preflight_worker_job(manager, invocation)
        if preflight_error is not None:
            return preflight_error
        result, job_object = _run_worker_job(
            manager, invocation, timeout=timeout, started=started
        )
        return result
    except WorkerVersionMismatch as exc:
        return build_worker_error("worker_version_mismatch", str(exc), job_id=job_id)
    except UnsupportedWorkerGuiError as exc:
        return build_worker_error("unsupported_worker_gui", str(exc), job_id=job_id)
    except ProtocolError as exc:
        return build_worker_error("worker_protocol_error", str(exc), job_id=job_id)
    except Exception as exc:
        manager._last_error = str(exc)
        return build_worker_error("worker_unavailable", str(exc), job_id=job_id)
    finally:
        manager._active_process = None
        manager._active_job_id = None
        if job_object is not None:
            job_object.close()
        shutil.rmtree(workspace, ignore_errors=True)
