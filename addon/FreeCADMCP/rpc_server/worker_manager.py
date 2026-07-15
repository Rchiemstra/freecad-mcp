"""Single isolated FreeCADCmd worker lifecycle (no pending queue)."""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .process_control import (
    WindowsJobObject,
    popen_platform_options,
    terminate_process_tree,
)
from .snapshot_service import materialize_load_aliases
from .worker_protocol import (
    MAX_ARTIFACT_BYTES,
    MAX_ARTIFACTS_TOTAL_BYTES,
    MAX_CODE_BYTES,
    MAX_RESULT_BYTES,
    MAX_STDOUT_BYTES,
    MAX_TEMP_ROOT_BYTES,
    ProtocolError,
    UnsupportedWorkerGuiError,
    clamp_timeout,
    read_json_limited,
    validate_job,
    write_json_atomic,
)


_VERSION_RE = re.compile(
    r"FreeCAD\s+(\d+)\.(\d+)\.(\d+)(?:[^\r\n]*?Revision:\s*([^\r\n]+))?"
)


class WorkerVersionMismatch(RuntimeError):
    pass


@dataclass(frozen=True)
class BuildIdentity:
    version: tuple[int, int, int]
    revision: str | None


def normalize_build_identity(values: tuple[str, str, str, str]) -> BuildIdentity:
    if len(values) != 4 or any(not str(value).strip() for value in values[:3]):
        raise WorkerVersionMismatch("missing or ambiguous FreeCAD version identity")
    try:
        version = tuple(int(str(value).strip()) for value in values[:3])
    except ValueError as exc:
        raise WorkerVersionMismatch("missing or ambiguous FreeCAD version identity") from exc
    raw_revision = str(values[3]).strip()
    if raw_revision.lower() in {"unknown", "none", "n/a", "ambiguous"}:
        raise WorkerVersionMismatch("missing or ambiguous FreeCAD revision identity")
    revision = raw_revision or None
    return BuildIdentity(version=version, revision=revision)  # type: ignore[arg-type]


def require_compatible_builds(
    gui_values: tuple[str, str, str, str],
    worker_values: tuple[str, str, str, str],
) -> None:
    gui = normalize_build_identity(gui_values)
    worker = normalize_build_identity(worker_values)
    if (gui.revision is None) != (worker.revision is None):
        raise WorkerVersionMismatch(
            f"development/release mismatch: GUI {gui}, worker {worker}"
        )
    if gui.revision is not None:
        if gui.version != worker.version or gui.revision != worker.revision:
            raise WorkerVersionMismatch(
                f"revision identity mismatch: GUI {gui}, worker {worker}"
            )
    elif gui.version != worker.version:
        raise WorkerVersionMismatch(
            f"stable release mismatch: GUI {gui.version}, worker {worker.version}"
        )


@dataclass(frozen=True)
class WorkerRuntime:
    gui_executable: str
    freecad_home: str
    gui_version: tuple[str, str, str, str]
    configured_path: str = ""


@dataclass
class _WorkerInvocation:
    job_id: str
    code: str
    options: dict[str, Any]
    snapshot: dict[str, Any]
    workspace: Path
    completed: threading.Event
    result: dict[str, Any] | None = None
    cancelled: bool = False


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
        self._stopping = False
        self._last_error: str | None = None
        self._executable: Path | None = None
        self._executable_version: tuple[str, str, str, str] | None = None
        self._sweep_stale_workspaces()
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="FreeCADMCP-WorkerManager",
            daemon=True,
        )
        self._worker_thread.start()

    def _candidate_paths(self) -> list[Path]:
        names = (
            ("FreeCADCmd.exe", "freecadcmd.exe")
            if sys.platform == "win32"
            else ("FreeCADCmd", "freecadcmd")
        )
        candidates: list[Path] = []
        gui = Path(self.runtime.gui_executable)
        candidates.extend(gui.with_name(name) for name in names)
        home_bin = Path(self.runtime.freecad_home) / "bin"
        candidates.extend(home_bin / name for name in names)
        if self.runtime.configured_path:
            candidates.append(Path(self.runtime.configured_path))
        env_path = os.environ.get("FREECAD_MCP_FREECADCMD")
        if env_path:
            candidates.append(Path(env_path))
        for name in names:
            found = shutil.which(name)
            if found:
                candidates.append(Path(found))
        unique = []
        seen = set()
        for candidate in candidates:
            key = os.path.normcase(os.path.abspath(str(candidate)))
            if key not in seen:
                seen.add(key)
                unique.append(candidate)
        return unique

    def _probe_version(self, candidate: Path) -> tuple[str, str, str, str]:
        completed = subprocess.run(
            [str(candidate), "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            **popen_platform_options(),
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        if completed.returncode != 0:
            raise RuntimeError(f"--version exited {completed.returncode}: {output.strip()}")
        match = _VERSION_RE.search(output)
        if not match:
            raise RuntimeError(f"could not parse FreeCAD version: {output.strip()}")
        groups = match.groups()
        return (
            groups[0].strip(),
            groups[1].strip(),
            groups[2].strip(),
            (groups[3] or "").strip(),
        )

    def discover_executable(self) -> Path:
        if self._executable is not None:
            return self._executable
        expected = self.runtime.gui_version
        failures = []
        mismatches = []
        for candidate in self._candidate_paths():
            if not candidate.is_file():
                continue
            try:
                actual = self._probe_version(candidate)
                require_compatible_builds(expected, actual)
                self._executable = candidate.resolve()
                self._executable_version = actual
                return self._executable
            except WorkerVersionMismatch as exc:
                message = f"{candidate}: {exc}"
                failures.append(message)
                mismatches.append(message)
            except Exception as exc:
                failures.append(f"{candidate}: {exc}")
        self._last_error = "; ".join(failures) or "No FreeCADCmd executable found"
        if mismatches:
            raise WorkerVersionMismatch(self._last_error)
        raise RuntimeError(self._last_error)

    def create_workspace(self) -> Path:
        if self._stopping:
            raise RuntimeError("server_stopping")
        self._sweep_stale_artifacts()
        if self._temp_usage() >= self.temp_root_limit_bytes:
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
        if self._temp_usage() > self.temp_root_limit_bytes:
            shutil.rmtree(workspace, ignore_errors=True)
            return self._error(
                "resource_limit_exceeded", "Managed temporary root exceeds its configured limit"
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
        invocation.completed.wait()
        return invocation.result or self._error(
            "worker_internal_error", "Worker invocation completed without a result", job_id=job_id
        )

    def _worker_loop(self) -> None:
        while True:
            try:
                invocation = self._work_queue.get(timeout=0.2)
            except queue.Empty:
                if self._stopping:
                    return
                continue
            try:
                if invocation.cancelled:
                    if invocation.result is None:
                        invocation.result = self._error(
                            "worker_cancelled", "Worker job was cancelled", job_id=invocation.job_id
                        )
                    shutil.rmtree(invocation.workspace, ignore_errors=True)
                elif self._stopping:
                    invocation.result = self._error(
                        "server_stopping", "Worker manager is stopping", job_id=invocation.job_id
                    )
                    shutil.rmtree(invocation.workspace, ignore_errors=True)
                else:
                    with self._state_lock:
                        self._active_invocation = invocation
                    invocation.result = self._execute_now(invocation)
            finally:
                with self._state_lock:
                    self._invocations.pop(invocation.job_id, None)
                    if self._active_invocation is invocation:
                        self._active_invocation = None
                invocation.completed.set()
                self._admission.release()
                self._work_queue.task_done()

    def _execute_now(self, invocation: _WorkerInvocation) -> dict[str, Any]:
        code = invocation.code
        options = invocation.options
        snapshot = invocation.snapshot
        workspace = invocation.workspace
        job_id = invocation.job_id
        timeout = clamp_timeout(options.get("timeout_seconds"))
        process = None
        job_object = None
        started = time.monotonic()
        try:
            if invocation.cancelled:
                return self._error(
                    "worker_cancelled", "Worker job was cancelled", job_id=job_id
                )
            if self._stopping:
                return self._error("server_stopping", "Worker manager is stopping")
            materialize_load_aliases(snapshot)
            if self._temp_usage() > self.temp_root_limit_bytes:
                return self._error(
                    "resource_limit_exceeded",
                    "Managed temporary root exceeds its configured limit after snapshot aliases",
                    job_id=job_id,
                )
            executable = self.discover_executable()
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
                "code": code,
                "options": {**options, "timeout_seconds": timeout},
                "artifact_directory": str(artifact_directory),
            }
            validate_job(job)
            write_json_atomic(job_path, job)
            entry = self.module_dir / "worker_entry.py"
            command = [str(executable), str(entry), "--pass", str(job_path)]
            log_path = workspace / "worker.log"
            if invocation.cancelled:
                return self._error(
                    "worker_cancelled", "Worker job was cancelled", job_id=job_id
                )
            with log_path.open("wb") as log:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=str(workspace),
                    **popen_platform_options(),
                )
                self._active_process = process
                self._active_job_id = job_id
                log_thread = threading.Thread(
                    target=self._drain_process_log,
                    args=(process, log),
                    name=f"FreeCADMCP-WorkerLog-{job_id}",
                    daemon=True,
                )
                log_thread.start()
                if sys.platform == "win32":
                    try:
                        job_object = WindowsJobObject()
                        job_object.assign(int(process._handle))  # type: ignore[attr-defined]
                    except Exception:
                        job_object = None
                deadline = time.monotonic() + timeout
                while True:
                    polled = process.poll()
                    if polled is not None:
                        return_code = polled
                        break
                    if self._temp_usage() > self.temp_root_limit_bytes:
                        terminated = terminate_process_tree(process, job_object)
                        log_thread.join(timeout=2.0)
                        return self._error(
                            "resource_limit_exceeded",
                            "Managed temporary root exceeded its configured runtime limit; "
                            f"process tree terminated={terminated}",
                            job_id=job_id,
                            duration_ms=(time.monotonic() - started) * 1000.0,
                        )
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    time.sleep(min(self.monitor_interval_seconds, remaining))
                if process.poll() is None:
                    terminated = terminate_process_tree(process, job_object)
                    log_thread.join(timeout=2.0)
                    return self._error(
                        "worker_timeout",
                        f"Worker exceeded {timeout:g}s; process tree terminated={terminated}",
                        job_id=job_id,
                        duration_ms=(time.monotonic() - started) * 1000.0,
                    )
                log_thread.join(timeout=2.0)
            if not result_path.exists():
                if invocation.cancelled:
                    return self._error(
                        "worker_cancelled", "Worker job was cancelled", job_id=job_id
                    )
                return self._error(
                    "worker_crash",
                    f"Worker exited {return_code} without result JSON",
                    job_id=job_id,
                )
            if result_path.stat().st_size > MAX_RESULT_BYTES:
                return self._error("worker_protocol_error", "Worker result exceeds 8 MiB", job_id=job_id)
            result = read_json_limited(result_path)
            if result.get("job_id") != job_id or result.get("schema_version") != 1:
                return self._error("worker_protocol_error", "Worker result identity mismatch", job_id=job_id)
            result.setdefault("metrics", {})["snapshot_duration_ms"] = snapshot.get(
                "snapshot_duration_ms", 0.0
            )
            execution = {
                "mode": "worker",
                "job_id": job_id,
                "duration_ms": (time.monotonic() - started) * 1000.0,
                "snapshot_duration_ms": snapshot.get("snapshot_duration_ms", 0.0),
            }
            if result.get("status") == "ok" and return_code == 0:
                try:
                    artifacts = self._promote_artifacts(
                        result.get("artifacts", []), artifact_directory, job_id
                    )
                except Exception as exc:
                    return self._error("resource_limit_exceeded", str(exc), job_id=job_id)
                return {
                    "success": True,
                    "message": "Python code execution completed.\nOutput: " + result.get("stdout", ""),
                    "recompute_errors": [],
                    "session": result.get("session", {}),
                    "structured": result.get("session", {}),
                    "execution": execution,
                    "artifacts": artifacts,
                    "stdout_truncated": bool(result.get("stdout_truncated")),
                }
            error = result.get("error") or {}
            if error.get("type") == "ExternalLinkUnresolved":
                error_code = "external_link_unresolved"
            elif error.get("type") == "ExternalSubelementUnresolved":
                error_code = "external_subelement_unresolved"
            elif error.get("type") == "ArtifactLimitError":
                error_code = "resource_limit_exceeded"
            elif error.get("type") == "UnsupportedWorkerGuiError":
                error_code = "unsupported_worker_gui"
            else:
                error_code = "worker_execution_error"
            return {
                "success": False,
                "is_error": True,
                "error_code": error_code,
                "error": error.get("message", f"Worker exited {return_code}"),
                "traceback": result.get("traceback"),
                "message": result.get("stdout", ""),
                "session": result.get("session", {}),
                "execution": execution,
            }
        except WorkerVersionMismatch as exc:
            return self._error("worker_version_mismatch", str(exc), job_id=job_id)
        except UnsupportedWorkerGuiError as exc:
            return self._error("unsupported_worker_gui", str(exc), job_id=job_id)
        except ProtocolError as exc:
            return self._error("worker_protocol_error", str(exc), job_id=job_id)
        except Exception as exc:
            self._last_error = str(exc)
            return self._error("worker_unavailable", str(exc), job_id=job_id)
        finally:
            self._active_process = None
            self._active_job_id = None
            if job_object is not None:
                job_object.close()
            shutil.rmtree(workspace, ignore_errors=True)

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
        terminated = terminate_process_tree(process) if process is not None else False
        return {
            "success": True,
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
        return {
            "available": available,
            "version": version,
            "executable": executable_name,
            "busy": self._active_process is not None,
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
        self._worker_thread.join(timeout=max(0.1, timeout))
        thread_stopped = not self._worker_thread.is_alive()
        if thread_stopped:
            shutil.rmtree(self.artifact_root, ignore_errors=True)
        return stopped and thread_stopped

    def _promote_artifacts(
        self, artifacts: Any, staging: Path, job_id: str
    ) -> list[dict[str, Any]]:
        if not isinstance(artifacts, list):
            raise ProtocolError("worker artifacts must be a list")
        staging = staging.resolve()
        destination = (self.artifact_root / job_id).resolve()
        total = 0
        promoted = []
        for index, item in enumerate(artifacts):
            if not isinstance(item, dict):
                raise ProtocolError("worker artifact entry must be an object")
            source = Path(item.get("path", "")).resolve()
            if staging not in source.parents or not source.is_file():
                raise ProtocolError("worker artifact escaped its staging directory")
            size = source.stat().st_size
            if size > MAX_ARTIFACT_BYTES:
                raise ProtocolError("individual artifact exceeds 256 MiB")
            total += size
            if total > MAX_ARTIFACTS_TOTAL_BYTES:
                raise ProtocolError("job artifacts exceed 512 MiB total")
            destination.mkdir(parents=True, exist_ok=True)
            target = destination / source.name
            os.replace(source, target)
            promoted.append({
                "artifact_id": f"{job_id}:{index}",
                "name": item.get("name", source.stem),
                "format": item.get("format", source.suffix.lstrip(".")),
                "path": str(target),
                "size_bytes": size,
                "expires_in_seconds": 3600,
            })
        return promoted

    def _temp_usage(self) -> int:
        """Measure managed files without following links outside the temp root."""
        total = 0
        pending = [self.temp_root]
        while pending:
            directory = pending.pop()
            try:
                entries = list(os.scandir(directory))
            except OSError:
                continue
            for entry in entries:
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                except OSError:
                    pass
        return total

    @staticmethod
    def _drain_process_log(process: subprocess.Popen, target) -> None:
        """Drain subprocess output continuously while retaining at most 1 MiB."""
        stream = process.stdout
        if stream is None:
            return
        retained = 0
        try:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    break
                remaining = max(0, MAX_STDOUT_BYTES - retained)
                if remaining:
                    data = chunk[:remaining]
                    target.write(data)
                    retained += len(data)
        finally:
            try:
                stream.close()
            except Exception:
                pass

    def _sweep_stale_workspaces(self) -> None:
        cutoff = time.time() - 24 * 60 * 60
        for child in self.temp_root.glob("mcp_worker_*"):
            try:
                if child.stat().st_mtime < cutoff:
                    shutil.rmtree(child, ignore_errors=True)
            except OSError:
                pass
        self._sweep_stale_artifacts()

    def _sweep_stale_artifacts(self) -> None:
        artifact_cutoff = time.time() - 60 * 60
        if self.artifact_root.exists():
            for child in self.artifact_root.iterdir():
                try:
                    if child.stat().st_mtime < artifact_cutoff:
                        shutil.rmtree(child, ignore_errors=True)
                except OSError:
                    pass

    @staticmethod
    def _error(error_code: str, error: str, **execution) -> dict[str, Any]:
        return {
            "success": False,
            "is_error": True,
            "error_code": error_code,
            "error": error,
            "execution": {"mode": "worker", **execution},
        }
