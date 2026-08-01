"""Helper functions for worker process monitoring and result mapping."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from typing import Any

from ..process_control import WindowsJobObject, terminate_process_tree
from ..telemetry import emit as emit_telemetry
from ..worker_protocol import MAX_RESULT_BYTES, read_json_limited
from .console import console_message
from .lifecycle_codes import build_worker_error
from .link_warnings import apply_link_warnings, merge_link_warnings
from .temp_usage import temp_usage
from .worker_invocation import WorkerInvocation


def wait_for_worker_process(
    manager,
    process: subprocess.Popen,
    job_object: WindowsJobObject | None,
    log_thread: threading.Thread,
    *,
    job_id: str,
    timeout: float,
    started: float,
) -> tuple[int | None, dict[str, Any] | None]:
    deadline = time.monotonic() + timeout
    return_code: int | None = None
    while True:
        polled = process.poll()
        if polled is not None:
            return_code = polled
            break
        if temp_usage(manager.temp_root) > manager.temp_root_limit_bytes:
            terminated = terminate_process_tree(process, job_object)
            log_thread.join(timeout=2.0)
            return None, build_worker_error(
                "resource_limit_exceeded",
                "Managed temporary root exceeded its configured runtime limit; "
                f"process tree terminated={terminated}",
                job_id=job_id,
                duration_ms=(time.monotonic() - started) * 1000.0,
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(manager.monitor_interval_seconds, remaining))
    if process.poll() is None:
        terminated = terminate_process_tree(process, job_object)
        log_thread.join(timeout=2.0)
        emit_telemetry(
            "worker_manager",
            "worker_job_timeout",
            status="timed_out",
            error_code="WORKER_TIMEOUT_DURING_EXECUTION",
            duration_ms=(time.monotonic() - started) * 1000.0,
            worker_job_id=job_id,
            payload={"terminated": terminated},
        )
        return None, build_worker_error(
            "worker_timeout",
            f"Worker exceeded {timeout:g}s; process tree terminated={terminated}",
            job_id=job_id,
            duration_ms=(time.monotonic() - started) * 1000.0,
        )
    log_thread.join(timeout=2.0)
    return return_code, None


def assign_windows_job_object(process: subprocess.Popen) -> WindowsJobObject | None:
    if sys.platform != "win32":
        return None
    try:
        job_object = WindowsJobObject()
        job_object.assign(int(process._handle))  # type: ignore[attr-defined]
        return job_object
    except Exception:
        return None


def worker_error_code(error: dict[str, Any]) -> str:
    error_type = error.get("type")
    if error_type == "ExternalLinkUnresolved":
        return "external_link_unresolved"
    if error_type == "ExternalSubelementUnresolved":
        return "external_subelement_unresolved"
    if error_type == "ArtifactLimitError":
        return "resource_limit_exceeded"
    if error_type == "UnsupportedWorkerGuiError":
        return "unsupported_worker_gui"
    return "worker_execution_error"


def build_worker_success_payload(
    manager,
    invocation: WorkerInvocation,
    result: dict[str, Any],
    *,
    return_code: int,
    started: float,
    artifact_directory,
) -> dict[str, Any]:
    job_id = invocation.job_id
    snapshot = invocation.snapshot
    execution = {
        "mode": "worker",
        "stage": "completed",
        "job_id": job_id,
        "duration_ms": (time.monotonic() - started) * 1000.0,
        "snapshot_duration_ms": snapshot.get("snapshot_duration_ms", 0.0),
    }
    artifacts = manager._promote_artifacts(
        result.get("artifacts", []), artifact_directory, job_id
    )
    payload = {
        "success": True,
        "message": (
            "Python code execution completed.\nOutput: " + result.get("stdout", "")
        ),
        "recompute_errors": [],
        "session": result.get("session", {}),
        "structured": result.get("session", {}),
        "execution": execution,
        "artifacts": artifacts,
        "stdout_truncated": bool(result.get("stdout_truncated")),
    }
    apply_link_warnings(payload, merge_link_warnings(snapshot, result))
    console_message(
        f"FreeCADMCP: worker IDLE job={job_id} ok duration={execution['duration_ms']:.0f}ms"
    )
    return payload


def build_worker_failure_payload(
    invocation: WorkerInvocation,
    result: dict[str, Any],
    *,
    return_code: int,
    started: float,
) -> dict[str, Any]:
    job_id = invocation.job_id
    snapshot = invocation.snapshot
    execution = {
        "mode": "worker",
        "stage": "completed",
        "job_id": job_id,
        "duration_ms": (time.monotonic() - started) * 1000.0,
        "snapshot_duration_ms": snapshot.get("snapshot_duration_ms", 0.0),
    }
    error = result.get("error") or {}
    error_code = worker_error_code(error)
    console_message(
        f"FreeCADMCP: worker IDLE job={job_id} failed error_code={error_code}"
    )
    error_payload = {
        "success": False,
        "is_error": True,
        "error_code": (
            "WORKER_TASK_FAILED" if error_code == "worker_execution_error" else error_code
        ),
        **(
            {"legacy_error_code": error_code}
            if error_code == "worker_execution_error"
            else {}
        ),
        "error": error.get("message", f"Worker exited {return_code}"),
        "traceback": result.get("traceback"),
        "message": result.get("stdout", ""),
        "session": result.get("session", {}),
        "execution": {**execution, "stage": "failed"},
    }
    apply_link_warnings(error_payload, merge_link_warnings(snapshot, result))
    return error_payload


def load_worker_result(
    invocation: WorkerInvocation,
    result_path,
    *,
    return_code: int | None,
    snapshot: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    job_id = invocation.job_id
    if not result_path.exists():
        if invocation.cancelled:
            return None, build_worker_error(
                "worker_cancelled", "Worker job was cancelled", job_id=job_id
            )
        return None, build_worker_error(
            "worker_crash",
            f"Worker exited {return_code} without result JSON",
            job_id=job_id,
        )
    if result_path.stat().st_size > MAX_RESULT_BYTES:
        return None, build_worker_error(
            "worker_protocol_error",
            "Worker result exceeds 8 MiB",
            job_id=job_id,
        )
    result = read_json_limited(result_path)
    if result.get("job_id") != job_id or result.get("schema_version") != 1:
        return None, build_worker_error(
            "worker_protocol_error",
            "Worker result identity mismatch",
            job_id=job_id,
        )
    result.setdefault("metrics", {})["snapshot_duration_ms"] = snapshot.get(
        "snapshot_duration_ms", 0.0
    )
    return result, None
