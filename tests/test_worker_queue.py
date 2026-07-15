"""Bounded Phase 6 worker admission and cancellation tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import shutil
import threading
import time

import FreeCADGui


if not hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand = lambda *_args, **_kwargs: None

from addon.FreeCADMCP.rpc_server.worker_manager import WorkerManager, WorkerRuntime


def _manager() -> WorkerManager:
    return WorkerManager(
        WorkerRuntime("FreeCAD", "/missing", ("0", "21", "0", "test")),
        "addon/FreeCADMCP/rpc_server",
    )


def test_one_active_three_pending_and_targeted_pending_cancellation(monkeypatch):
    manager = _manager()
    active_started = threading.Event()
    release_active = threading.Event()

    def fake_execute(invocation):
        active_started.set()
        release_active.wait(timeout=5)
        shutil.rmtree(invocation.workspace, ignore_errors=True)
        return {"success": True, "execution": {"job_id": invocation.job_id}}

    monkeypatch.setattr(manager, "_execute_now", fake_execute)
    pool = ThreadPoolExecutor(max_workers=5)
    try:
        futures = [
            pool.submit(manager.execute, "print(1)", {}, {}, manager.create_workspace())
            for _ in range(4)
        ]
        assert active_started.wait(timeout=2)
        deadline = time.monotonic() + 2
        while manager.status()["queue_depth"] != 3 and time.monotonic() < deadline:
            time.sleep(0.01)
        status = manager.status()
        assert status["queue_depth"] == 3
        assert len(status["pending_job_ids"]) == 3

        saturated = manager.execute("print(2)", {}, {}, manager.create_workspace())
        assert saturated["error_code"] == "worker_queue_full"

        cancelled_id = status["pending_job_ids"][0]
        cancellation = manager.cancel(cancelled_id)
        assert cancellation["success"] is True
        assert cancellation["state"] == "pending"
        release_active.set()
        results = [future.result(timeout=5) for future in futures]
        cancelled = [r for r in results if r.get("error_code") == "worker_cancelled"]
        assert len(cancelled) == 1
        assert cancelled[0]["execution"]["job_id"] == cancelled_id
    finally:
        release_active.set()
        pool.shutdown(wait=True, cancel_futures=True)
        manager.stop()


def test_unknown_cancellation_target_is_structured():
    manager = _manager()
    try:
        result = manager.cancel("missing-job")
        assert result == {
            "success": False,
            "error_code": "worker_job_not_found",
            "job_id": "missing-job",
        }
    finally:
        manager.stop()
