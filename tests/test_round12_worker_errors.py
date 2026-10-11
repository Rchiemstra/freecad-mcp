from types import SimpleNamespace as NS
import time
import pytest
from addon.FreeCADMCP.rpc_server.worker_manager_ops.execute_job_helpers import build_worker_failure_payload

pytestmark = pytest.mark.unit


def failure(stdout=""):
    invocation = NS(job_id="qa", snapshot={})
    return build_worker_failure_payload(invocation, {
        "error": {"type": "RuntimeError", "message": "qa boom"},
        "traceback": 'Traceback (most recent call last):\n  File "<string>", line 2\nRuntimeError: qa boom',
        "stdout": stdout}, return_code=1, started=time.monotonic())


def test_failure_is_not_success():
    assert not failure()["success"]


def test_failure_has_exception_and_traceback_not_stdout():
    result = failure("GROUP ['box']")
    assert "RuntimeError: qa boom" in result["error"]
    assert 'File "<string>", line 2' in result["error"]
    assert "GROUP" not in result["error"]


def test_last_failure_survives_status_until_next_job_starts(monkeypatch):
    from tests.worker.test_worker_queue import _manager
    manager = _manager()
    monkeypatch.setattr(manager, "discover_executable", lambda: __import__("pathlib").Path("/fake/FreeCADCmd"))
    monkeypatch.setattr(manager, '_execute_now', lambda job: failure())
    try:
        manager.execute('raise RuntimeError("qa boom")', {}, {}, manager.create_workspace())
        assert 'qa boom' in manager.status()['last_error']
        assert 'qa boom' in manager.status()['last_error']
        def success(job):
            assert manager._last_error is None
            return {'success': True}
        monkeypatch.setattr(manager, '_execute_now', success)
        assert manager.execute('pass', {}, {}, manager.create_workspace())['success']
        assert manager.status()['last_error'] is None
    finally:
        manager.stop()
