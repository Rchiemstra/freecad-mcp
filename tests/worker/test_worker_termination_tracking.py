"""A worker that survives termination stays owned by its manager.

Ending the job used to drop the Popen, free the admission slot, delete the
workspace, and let stop() release the artifact-root lock. The process was
still running and could keep writing that workspace.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from addon.FreeCADMCP.rpc_server.worker_manager import WorkerManager, WorkerRuntime
from addon.FreeCADMCP.rpc_server.worker_manager_ops import artifact_roots
from addon.FreeCADMCP.rpc_server.worker_manager_ops.execute_job_helpers import (
    wait_for_worker_process,
)

pytestmark = pytest.mark.unit

_SNAPSHOT = {"primary_document": "Doc", "documents": {"Doc": {}}}
_CHILD = (
    "import os, time, pathlib\n"
    "path = pathlib.Path(os.environ['FREECAD_MCP_WORKER_MARKER'])\n"
    "while True:\n"
    "    try:\n"
    "        path.write_text(str(time.time()))\n"
    "    except OSError:\n"
    "        pass\n"
    "    time.sleep(0.05)\n"
)


def _runtime() -> WorkerRuntime:
    return WorkerRuntime("FreeCAD", "/missing", ("1", "2", "3", ""))


def _kill(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        process.kill()
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=2)


def _refuse_termination(*_args, **_kwargs) -> bool:
    return False


def _patch_launch(monkeypatch, launches: list[str], processes: list[subprocess.Popen]):
    import addon.FreeCADMCP.rpc_server.worker_manager_ops.execute_job as execute_job
    from addon.FreeCADMCP.rpc_server.worker_manager_ops import retained_worker

    def fake_launch(manager, invocation, *, command, workspace, timeout, started, log_path):
        del command, log_path
        env = os.environ.copy()
        env["FREECAD_MCP_WORKER_MARKER"] = str(Path(workspace) / "still-writing.txt")
        process = subprocess.Popen(
            [sys.executable, "-c", _CHILD],
            cwd=str(workspace),
            env=env,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Publish the handle before the launch signal. The test waits on
        # `launches`, and under load that wait can win the race otherwise.
        processes.append(process)
        launches.append(invocation.job_id)
        manager._active_process = process
        manager._active_job_id = invocation.job_id
        log_thread = threading.Thread(target=lambda: None, daemon=True)
        log_thread.start()
        return_code, early = wait_for_worker_process(
            manager,
            process,
            None,
            log_thread,
            job_id=invocation.job_id,
            timeout=timeout,
            started=started,
        )
        return return_code, process, None, early

    monkeypatch.setattr(execute_job, "discover_executable", lambda _manager: Path(sys.executable))
    monkeypatch.setattr(execute_job, "materialize_load_aliases", lambda _snapshot: None)
    monkeypatch.setattr(execute_job, "launch_and_wait_for_worker", fake_launch)
    monkeypatch.setattr(retained_worker, "terminate_process_tree", _refuse_termination)


def _manager(tmp_path: Path) -> WorkerManager:
    return WorkerManager(
        _runtime(),
        "addon/FreeCADMCP/rpc_server",
        temp_root=tmp_path / "workers",
        monitor_interval_seconds=0.05,
    )


def _ownership(manager: WorkerManager, process: subprocess.Popen, workspace: Path) -> dict:
    status = manager.status()
    marker = workspace / "still-writing.txt"
    return {
        "tracked": manager._active_process is process,
        "alive": process.poll() is None,
        "workspace": workspace.exists(),
        "marker": marker.is_file(),
        "busy": status["busy"],
        "active_job_id": status["active_job_id"],
        "lock_held": not artifact_roots._lock_is_abandoned(manager._artifact_owner.lock_path),
        "artifact_root": manager.artifact_root.exists(),
    }


def test_failed_termination_keeps_process_slot_workspace_and_artifact_lock(
    tmp_path, monkeypatch
):
    """Timeout and cancel both give up; the live process must still occupy its slot."""

    launches: list[str] = []
    processes: list[subprocess.Popen] = []
    _patch_launch(monkeypatch, launches, processes)
    manager = _manager(tmp_path)
    workspace = manager.create_workspace()
    outcome: dict = {}

    def run() -> None:
        outcome["result"] = manager.execute(
            "print(1)",
            {"timeout_seconds": 1},
            _SNAPSHOT,
            workspace,
        )

    worker = threading.Thread(target=run)
    worker.start()
    try:
        deadline = time.monotonic() + 5
        while (not launches or not processes) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert launches and processes, "worker never launched"
        process = processes[0]
        job_id = launches[0]
        cancellation = manager.cancel(job_id)
        assert cancellation["error_code"] == "WORKER_TERMINATION_FAILED"
        assert cancellation["terminated"] is False
        held_during_cancel = _ownership(manager, process, workspace)
        assert held_during_cancel["tracked"] is True
        assert held_during_cancel["alive"] is True
        assert held_during_cancel["workspace"] is True

        worker.join(timeout=5)
        assert not worker.is_alive()
        result = outcome["result"]
        assert result["legacy_error_code"] == "worker_timeout"
        assert "terminated=False" in result["error"]
        assert result["execution"]["job_id"] == job_id

        second: dict = {}

        def run_second() -> None:
            second["result"] = manager.execute(
                "print(2)",
                {"timeout_seconds": 1},
                _SNAPSHOT,
                manager.create_workspace(),
            )

        queued = threading.Thread(target=run_second)
        queued.start()
        queue_deadline = time.monotonic() + 2
        while manager.status()["queue_depth"] < 1 and time.monotonic() < queue_deadline:
            time.sleep(0.01)
        after_timeout = _ownership(manager, process, workspace)
        assert after_timeout == {
            "tracked": True,
            "alive": True,
            "workspace": True,
            "marker": True,
            "busy": True,
            "active_job_id": job_id,
            "lock_held": True,
            "artifact_root": True,
        }
        assert launches == [job_id]
        first_write = (workspace / "still-writing.txt").read_text()
        time.sleep(0.2)
        assert (workspace / "still-writing.txt").read_text() != first_write

        assert manager.stop(timeout=0.4) is False
        after_stop = _ownership(manager, process, workspace)
        assert after_stop["tracked"] is True
        assert after_stop["alive"] is True
        assert after_stop["workspace"] is True
        assert after_stop["marker"] is True
        assert after_stop["lock_held"] is True
        assert after_stop["artifact_root"] is True
        artifact_roots.reap_orphaned_artifact_roots(manager.temp_root, tmp_path / "peer")
        assert manager.artifact_root.exists()
        assert manager._worker_thread.is_alive()

        _kill(process)
        deadline = time.monotonic() + 3
        while manager._worker_thread.is_alive() and time.monotonic() < deadline:
            for item in processes:
                _kill(item)
            time.sleep(0.05)
        assert not manager._worker_thread.is_alive()
        assert not workspace.exists()
        assert manager._active_process is None
        assert not manager.artifact_root.exists()
        assert not manager._artifact_owner.lock_path.exists()
    finally:
        for process in processes:
            _kill(process)
        queued_thread = locals().get("queued")
        if isinstance(queued_thread, threading.Thread):
            queued_thread.join(timeout=5)
        worker.join(timeout=5)
        manager.stop()


def test_quota_kill_failure_keeps_the_process_until_it_exits(tmp_path, monkeypatch):
    """The runtime quota path is the same ownership rule as a timeout."""

    launches: list[str] = []
    processes: list[subprocess.Popen] = []
    _patch_launch(monkeypatch, launches, processes)
    import addon.FreeCADMCP.rpc_server.worker_manager_ops.execute_job_helpers as helpers

    manager = _manager(tmp_path)
    monkeypatch.setattr(
        helpers,
        "temp_usage",
        lambda _root: manager.temp_root_limit_bytes + 1,
    )
    workspace = manager.create_workspace()
    try:
        result = manager.execute(
            "print(1)",
            {"timeout_seconds": 30},
            _SNAPSHOT,
            workspace,
        )
        process = processes[0]
        assert result["error_code"] == "resource_limit_exceeded"
        assert "terminated=False" in result["error"]
        assert _ownership(manager, process, workspace)["tracked"] is True
        assert process.poll() is None
        assert workspace.exists()
        assert manager.status()["busy"] is True
        assert launches == [result["execution"]["job_id"]]

        _kill(process)
        # The handle is cleared before the workspace is removed, so busy can
        # drop while rmtree is still walking the directory.
        deadline = time.monotonic() + 3
        while (
            manager.status()["busy"] or workspace.exists()
        ) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert manager.status()["busy"] is False
        assert not workspace.exists()
        assert manager._active_process is None
        assert manager.stop() is True
        assert not manager.artifact_root.exists()
        assert not manager._artifact_owner.lock_path.exists()
    finally:
        for process in processes:
            _kill(process)
        manager.stop()


def test_successful_termination_still_reaps_the_workspace(tmp_path, monkeypatch):
    """A kill that actually exits the process still frees the slot and the files."""

    launches: list[str] = []
    processes: list[subprocess.Popen] = []
    _patch_launch(monkeypatch, launches, processes)
    from addon.FreeCADMCP.rpc_server.process_control import terminate_process_tree
    from addon.FreeCADMCP.rpc_server.worker_manager_ops import retained_worker

    monkeypatch.setattr(retained_worker, "terminate_process_tree", terminate_process_tree)
    manager = _manager(tmp_path)
    workspace = manager.create_workspace()
    try:
        result = manager.execute(
            "print(1)",
            {"timeout_seconds": 1},
            _SNAPSHOT,
            workspace,
        )
        process = processes[0]
        assert result["legacy_error_code"] == "worker_timeout"
        assert "terminated=True" in result["error"]
        assert process.poll() is not None
        assert not workspace.exists()
        assert manager.status()["busy"] is False
        assert manager._active_process is None
        assert manager.stop() is True
        assert not manager.artifact_root.exists()
    finally:
        for process in processes:
            _kill(process)
        manager.stop()
