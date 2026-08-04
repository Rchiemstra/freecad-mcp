"""Single isolated FreeCADCmd worker lifecycle (no pending queue)."""

from __future__ import annotations

import queue
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

from .process_control import terminate_process_tree
from .telemetry import emit as emit_telemetry
from .worker_manager_ops.build_identity import (
    BuildIdentity,
    normalize_build_identity,
    require_compatible_builds,
)
from .worker_manager_ops.executable_discovery import (
    VERSION_PROBE_TIMEOUT_SECONDS,
    discover_executable,
)
from .worker_manager_ops.lifecycle_codes import build_worker_error
from .worker_manager_ops.link_warnings import apply_link_warnings, merge_link_warnings
from .worker_manager_ops.surfaces import attach_worker_manager_surfaces
from .worker_manager_ops.temp_usage import (
    sweep_stale_artifacts,
    sweep_stale_workspaces,
    temp_usage,
)
from .worker_manager_ops.worker_invocation import WorkerInvocation as _WorkerInvocation
from .worker_manager_ops.worker_loop import worker_loop
from .worker_manager_ops.worker_runtime import WorkerRuntime
from .worker_manager_ops.worker_version_mismatch import WorkerVersionMismatch
from .worker_protocol_ops.constants import (
    MAX_ARTIFACT_BYTES,
    MAX_ARTIFACTS_TOTAL_BYTES,
    MAX_CODE_BYTES,
    MAX_TEMP_ROOT_BYTES,
)

# §3.3 compatibility shims for deep test imports.
_merge_link_warnings = merge_link_warnings
_apply_link_warnings = apply_link_warnings


class WorkerManager:
    """Run one worker with bounded admission: one active and three pending."""

    def __init__(
        self,
        runtime: WorkerRuntime,
        module_dir: str,
        *,
        temp_root: str | Path | None = None,
        temp_root_limit_bytes: int = MAX_TEMP_ROOT_BYTES,
        monitor_interval_seconds: float = 0.1,
        autostart: bool = True,
    ):
        self.runtime = runtime
        self.module_dir = Path(module_dir)
        self.temp_root = (
            Path(temp_root)
            if temp_root is not None
            else Path(tempfile.gettempdir()) / "freecad_mcp_workers"
        )
        self.temp_root_limit_bytes = int(temp_root_limit_bytes)
        self.monitor_interval_seconds = max(0.01, float(monitor_interval_seconds))
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.artifact_root = self.temp_root / "artifacts"
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self._state_lock = threading.Lock()
        self._active_process: subprocess.Popen | None = None
        self._active_job_id: str | None = None
        self._active_invocation: _WorkerInvocation | None = None
        self._invocations: dict[str, _WorkerInvocation] = {}
        self._work_queue: queue.Queue[_WorkerInvocation] = queue.Queue()
        self._admission = threading.BoundedSemaphore(4)
        self._start_lock = threading.Lock()
        self._worker_started = False
        self._stopping = False
        self._last_error: str | None = None
        self._executable: Path | None = None
        self._executable_version: tuple[str, str, str, str] | None = None
        sweep_stale_workspaces(self.temp_root, self.artifact_root)
        self._worker_thread = threading.Thread(
            target=worker_loop,
            args=(self,),
            name="FreeCADMCP-WorkerManager",
            daemon=True,
        )
        if autostart:
            self._start()

    def _start(self) -> None:
        """Start queue processing once, after all runtime dependencies exist."""

        with self._start_lock:
            if self._worker_started:
                return
            if self._stopping:
                raise RuntimeError("server_stopping")
            self._worker_thread.start()
            self._worker_started = True

    def discover_executable(self) -> Path:
        return discover_executable(self)

    def create_workspace(self) -> Path:
        if self._stopping:
            raise RuntimeError("server_stopping")
        sweep_stale_artifacts(self.artifact_root)
        if temp_usage(self.temp_root) >= self.temp_root_limit_bytes:
            raise RuntimeError("temporary worker root exceeds its configured limit")
        return Path(tempfile.mkdtemp(prefix="mcp_worker_", dir=self.temp_root))

    def execute(
        self,
        code: str,
        options: dict[str, Any],
        snapshot: dict[str, Any],
        workspace: Path,
    ) -> dict[str, Any]:
        if len(code.encode("utf-8")) > MAX_CODE_BYTES:
            return self._error("resource_limit_exceeded", "Worker code exceeds 1 MiB")
        if temp_usage(self.temp_root) > self.temp_root_limit_bytes:
            shutil.rmtree(workspace, ignore_errors=True)
            return self._error(
                "resource_limit_exceeded",
                "Managed temporary root exceeds its configured limit",
            )
        job_id = str(uuid.uuid4())
        if self._stopping:
            shutil.rmtree(workspace, ignore_errors=True)
            return self._error("server_stopping", "Worker manager is stopping", job_id=job_id)
        if not self._admission.acquire(blocking=False):
            shutil.rmtree(workspace, ignore_errors=True)
            return self._error(
                "worker_queue_full",
                "Worker capacity is full (one active and three pending)",
                job_id=job_id,
            )
        invocation = _WorkerInvocation(
            job_id=job_id,
            code=code,
            options=dict(options),
            snapshot=snapshot,
            workspace=workspace,
            completed=threading.Event(),
        )
        with self._state_lock:
            if self._stopping:
                self._admission.release()
                shutil.rmtree(workspace, ignore_errors=True)
                return self._error("server_stopping", "Worker manager is stopping", job_id=job_id)
            self._invocations[job_id] = invocation
            self._work_queue.put_nowait(invocation)
        emit_telemetry(
            "worker_manager",
            "worker_job_created",
            worker_job_id=job_id,
            payload={
                "primary_document": snapshot.get("primary_document"),
                "timeout_seconds": options.get("timeout_seconds"),
            },
        )
        invocation.completed.wait()
        return invocation.result or self._error(
            "worker_internal_error",
            "Worker invocation completed without a result",
            job_id=job_id,
        )

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._state_lock:
            invocation = self._invocations.get(job_id)
            if invocation is None:
                return {"success": False, "error_code": "worker_job_not_found", "job_id": job_id}
            invocation.cancelled = True
            active = self._active_invocation is invocation
            process = self._active_process if active else None
            if not active and invocation.result is None:
                invocation.result = self._error(
                    "worker_cancelled", "Pending worker job was cancelled", job_id=job_id
                )
                invocation.completed.set()
        emit_telemetry(
            "worker_manager",
            "worker_job_cancel_requested",
            status="warning",
            error_code="WORKER_CANCEL_REQUESTED",
            worker_job_id=job_id,
            payload={"state": "active" if active else "pending"},
        )
        terminated = terminate_process_tree(process) if process is not None else False
        if active and process is not None and not terminated:
            return {
                "success": False,
                "error_code": "WORKER_TERMINATION_FAILED",
                "legacy_error_code": "worker_termination_failed",
                "error": "The active worker process tree could not be terminated",
                "job_id": job_id,
                "state": "active",
                "termination_requested": True,
                "terminated": False,
            }
        return {
            "success": True,
            "cancellation_code": "WORKER_CANCEL_REQUESTED",
            "job_id": job_id,
            "state": "active" if active else "pending",
            "termination_requested": active,
            "terminated": terminated,
        }

    def status(self) -> dict[str, Any]:
        available = False
        version = None
        try:
            executable = self.discover_executable()
            available = True
            version = ".".join(self._executable_version[:3]) if self._executable_version else None
            executable_name = executable.name
        except Exception:
            executable_name = None
        with self._state_lock:
            active_job_id = self._active_job_id
            pending_job_ids = [
                job_id
                for job_id, invocation in self._invocations.items()
                if invocation is not self._active_invocation and not invocation.cancelled
            ]
        busy = self._active_process is not None
        if not available:
            state = "unavailable"
        elif busy:
            state = "busy"
        else:
            state = "idle"
        return {
            "available": available,
            "state": state,
            "version": version,
            "executable": executable_name,
            "busy": busy,
            "active_job_id": active_job_id,
            "queue_depth": len(pending_job_ids),
            "pending_job_ids": pending_job_ids,
            "queue_capacity": 3,
            "last_error": self._last_error,
        }

    def stop(self, timeout: float = 4.0) -> bool:
        self._stopping = True
        with self._state_lock:
            invocations = list(self._invocations.values())
            active = self._active_invocation
            process = self._active_process
            for invocation in invocations:
                invocation.cancelled = True
                if invocation is not active:
                    invocation.result = self._error(
                        "server_stopping", "Worker manager is stopping", job_id=invocation.job_id
                    )
                    invocation.completed.set()
        stopped = True if process is None else terminate_process_tree(
            process, grace=min(timeout, 2.0)
        )
        with self._start_lock:
            worker_started = self._worker_started
        if worker_started:
            self._worker_thread.join(timeout=max(0.1, timeout))
        thread_stopped = not worker_started or not self._worker_thread.is_alive()
        if thread_stopped:
            shutil.rmtree(self.artifact_root, ignore_errors=True)
        return stopped and thread_stopped

    @staticmethod
    def _error(error_code: str, error: str, **execution) -> dict[str, Any]:
        return build_worker_error(error_code, error, **execution)


attach_worker_manager_surfaces(WorkerManager)

__all__ = [
    "MAX_ARTIFACTS_TOTAL_BYTES",
    "MAX_ARTIFACT_BYTES",
    "VERSION_PROBE_TIMEOUT_SECONDS",
    "BuildIdentity",
    "WorkerManager",
    "WorkerRuntime",
    "WorkerVersionMismatch",
    "_WorkerInvocation",
    "_apply_link_warnings",
    "_merge_link_warnings",
    "normalize_build_identity",
    "require_compatible_builds",
    "subprocess",
]
