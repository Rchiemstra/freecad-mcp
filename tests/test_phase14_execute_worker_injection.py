"""Focused contracts for Phase 14 execute-code and worker injection."""

from __future__ import annotations

import ast
import io
import threading
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server import rpc_server
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import (
    execute_code as execute_code_module,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_exec import (
    run_python_on_gui_thread,
)
from addon.FreeCADMCP.rpc_server.methods.lifecycle_methods_ops import worker_ops

pytestmark = pytest.mark.unit


ROOT = Path(__file__).resolve().parents[1]
EXECUTE_DIR = (
    ROOT
    / "addon"
    / "FreeCADMCP"
    / "rpc_server"
    / "methods"
    / "cad_methods_ops"
)
WORKER_OPS = (
    ROOT
    / "addon"
    / "FreeCADMCP"
    / "rpc_server"
    / "methods"
    / "lifecycle_methods_ops"
    / "worker_ops.py"
)


class _CompatibilityAPI:
    def __init__(self, *, invoke_callback: bool = True, native_result=None) -> None:
        self.invoke_callback = invoke_callback
        self.native_result = native_result or {
            "status": "Committed",
            "committed": True,
            "revisions": {"UnknownModel": 9},
        }
        self.calls = []
        self.structural_scopes = []
        self.callback_results = []
        self.callback_failures = 0

    def commit_compatibility_mutation(
        self, document_name, callback, *, structural=False
    ):
        self.calls.append((document_name, callback))
        self.structural_scopes.append(structural)
        if not self.invoke_callback:
            return {"status": "Rejected", "committed": False}
        try:
            result = callback()
        except Exception:
            self.callback_failures += 1
            raise
        self.callback_results.append(result)
        return self.native_result


def _rpc_with_execution(**overrides):
    initial = rpc_server.FreeCADRPC()
    compatibility_api = overrides.pop(
        "compatibility_api", initial._collaboration_collaborators.compatibility_api
    )
    freecad = overrides.pop("freecad", None)
    collab_kwargs = {"compatibility_api": compatibility_api}
    exec_kwargs = {"compatibility_api": compatibility_api, **overrides}
    cad_kwargs = {"compatibility_api": compatibility_api}
    if freecad is not None:
        collab_kwargs["freecad"] = freecad
        exec_kwargs["freecad"] = freecad
        cad_kwargs["freecad"] = freecad
    collaboration = replace(
        initial._collaboration_collaborators,
        **collab_kwargs,
    )
    execution = replace(
        initial._execution_collaborators,
        **exec_kwargs,
    )
    cad = replace(initial._cad_collaborators, **cad_kwargs)
    return rpc_server.FreeCADRPC(
        collaboration_collaborators=collaboration,
        execution_collaborators=execution,
        cad_collaborators=cad,
    )


def test_execute_and_worker_modules_have_no_runtime_locator_or_safety_import():
    paths = sorted(EXECUTE_DIR.glob("execute_code*.py")) + [WORKER_OPS]
    assert len(paths) == 11
    for path in paths:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        assert "_rpc_mod" not in source, path
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert not any(
            name.endswith(("execute_code_analysis", "execution_safety"))
            for name in imported
        ), path


def test_mutating_gui_execute_uses_native_boundary_exactly_once_and_keeps_result(
    monkeypatch,
):
    api = _CompatibilityAPI()
    safety_calls = []

    def analyze(code, options):
        safety_calls.append(("analyze", code, options))
        return {"document_scope": ["Model"], "call_families": []}

    def warning(analysis):
        safety_calls.append(("warning", analysis))

    def geometry(code):
        safety_calls.append(("geometry", code))

    def blocking(code, *, read_only):
        safety_calls.append(("blocking", code, read_only))

    rpc = _rpc_with_execution(
        compatibility_api=api,
        analyze_execute_code=analyze,
        typed_tool_warning=warning,
        find_gui_geometry_loop_risk=geometry,
        find_gui_blocking_risk=blocking,
        execute_timeout=17.0,
    )
    monkeypatch.setattr(rpc, "_collect_invalid_objects", dict)
    monkeypatch.setattr(
        execute_code_module,
        "run_execute_code_gui_task",
        lambda *_args, **_kwargs: {
            "ok": True,
            "session": {"saved": False},
            "stdout": "kept",
        },
    )
    dispatches = []

    def dispatch(task, timeout):
        dispatches.append(timeout)
        return task()

    monkeypatch.setattr(rpc, "_dispatch_gui", dispatch)

    result = rpc.execute_code(
        "print('kept')",
        {"document": "Model", "execution_mode": "gui"},
    )

    assert [item[0] for item in api.calls] == ["Model"]
    assert api.structural_scopes == [True]
    assert api.callback_results == [
        {"ok": True, "session": {"saved": False}, "stdout": "kept"}
    ]
    assert dispatches == [17.0]
    assert result["success"] is True
    assert result["message"] == "Python code execution completed.\nOutput: kept"
    assert result["session"] == {"saved": False}
    assert [item[0] for item in safety_calls] == [
        "analyze",
        "warning",
        "geometry",
        "blocking",
    ]


def test_read_only_worker_execute_never_enters_native_boundary(monkeypatch):
    api = _CompatibilityAPI()
    rpc = _rpc_with_execution(compatibility_api=api)
    worker_result = {"success": True, "execution": {"mode": "worker"}}
    monkeypatch.setattr(rpc, "_execute_code_worker", lambda *_args: worker_result)

    result = rpc.execute_code(
        "print(1)",
        {"document": "Model", "read_only": True, "execution_mode": "worker"},
    )

    assert result["success"] is True
    assert result["execution"] == {"mode": "worker"}
    assert api.calls == []


def test_native_rejection_without_callback_fails_closed_in_execute_envelope(
    monkeypatch,
):
    api = _CompatibilityAPI(invoke_callback=False)
    rpc = _rpc_with_execution(compatibility_api=api)
    monkeypatch.setattr(rpc, "_collect_invalid_objects", dict)
    monkeypatch.setattr(rpc, "_dispatch_gui", lambda task, _timeout: task())
    gui_calls = []
    monkeypatch.setattr(
        execute_code_module,
        "run_execute_code_gui_task",
        lambda *_args, **_kwargs: gui_calls.append(True),
    )

    result = rpc.execute_code(
        "print('must not run')",
        {"document": "Model", "execution_mode": "gui"},
    )

    assert [item[0] for item in api.calls] == ["Model"]
    assert gui_calls == []
    assert result["success"] is False
    assert result["is_error"] is True
    assert result["error"] == "Native compatibility mutation rejected execution (Rejected)"


def test_native_rejection_after_callback_fails_closed_in_execute_envelope(
    monkeypatch,
):
    api = _CompatibilityAPI(
        native_result={"status": "PostconditionFailed", "committed": False}
    )
    rpc = _rpc_with_execution(compatibility_api=api)
    monkeypatch.setattr(rpc, "_collect_invalid_objects", dict)
    monkeypatch.setattr(rpc, "_dispatch_gui", lambda task, _timeout: task())
    gui_calls = []
    monkeypatch.setattr(
        execute_code_module,
        "run_execute_code_gui_task",
        lambda *_args, **_kwargs: gui_calls.append(True)
        or {"ok": True, "session": {}, "stdout": "must not publish"},
    )

    result = rpc.execute_code(
        "print('must fail closed')",
        {"document": "Model", "execution_mode": "gui"},
    )

    assert gui_calls == [True]
    assert result["success"] is False
    assert result["is_error"] is True
    assert result["error"] == (
        "Native compatibility mutation rejected execution (PostconditionFailed)"
    )


def test_gui_error_requests_native_rollback_and_preserves_error_envelope(monkeypatch):
    api = _CompatibilityAPI()
    rpc = _rpc_with_execution(compatibility_api=api)
    monkeypatch.setattr(rpc, "_collect_invalid_objects", dict)
    monkeypatch.setattr(rpc, "_dispatch_gui", lambda task, _timeout: task())
    monkeypatch.setattr(
        execute_code_module,
        "run_execute_code_gui_task",
        lambda *_args, **_kwargs: {
            "ok": False,
            "error": "historical execute failure",
            "traceback": "traceback-contract",
            "session": {"saved": False},
            "stdout": "partial output",
        },
    )

    result = rpc.execute_code(
        "raise RuntimeError('fail')",
        {"document": "Model", "execution_mode": "gui"},
    )

    assert api.callback_failures == 1
    assert api.callback_results == []
    assert result["success"] is False
    assert result["error"] == "historical execute failure"
    assert result["traceback"] == "traceback-contract"
    assert result["session"] == {"saved": False}
    assert result["message"] == "partial output"


def test_gui_execute_preserves_the_historical_persistent_namespace() -> None:
    freecad = SimpleNamespace(
        Console=SimpleNamespace(PrintMessage=lambda _message: None)
    )
    first_output = io.StringIO()
    second_output = io.StringIO()

    assert run_python_on_gui_thread(
        "phase14_persistent_value = 41", first_output, freecad=freecad
    ) == (True, None)
    assert run_python_on_gui_thread(
        "print(phase14_persistent_value + 1)", second_output, freecad=freecad
    ) == (True, None)
    assert second_output.getvalue() == "42\n"


def test_worker_execution_uses_only_captured_worker_and_snapshot_dependencies(
    tmp_path, monkeypatch
):
    events = []

    class Manager:
        def create_workspace(self):
            events.append("workspace")
            workspace = tmp_path / "worker"
            workspace.mkdir()
            return workspace

        def execute(self, code, options, snapshot, workspace):
            events.append(("execute", code, options, snapshot, workspace))
            return {"success": True, "snapshot": snapshot}

    class Coordinator:
        def __enter__(self):
            events.append("lock_enter")

        def __exit__(self, *_args):
            events.append("lock_exit")

    manager = Manager()
    mutation_context = {
        "generations": {"Model": 3},
        "request_id": "request-1",
        "document_keys": ("Model",),
    }

    def snapshot_context():
        events.append("context")
        return mutation_context

    def create_snapshot(document_name, workspace, **kwargs):
        events.append(("snapshot", document_name, workspace, kwargs))
        return {"ok": True, "documents": [{"document_name": document_name}]}

    rpc = _rpc_with_execution(
        worker_manager=manager,
        snapshot_coordinator=Coordinator(),
        snapshot_mutation_context_for_request=snapshot_context,
        create_primary_snapshot_gui=create_snapshot,
    )
    monkeypatch.setattr(rpc, "_dispatch_snapshot_gui", lambda task: task())

    result = rpc._execute_code_worker("print(1)", {"document": "Model"})

    assert result["success"] is True
    assert events[:3] == ["workspace", "context", "lock_enter"]
    assert events[3][0] == "snapshot"
    assert events[3][3]["mutation_generations"] == {"Model": 3}
    assert events[3][3]["mutation_request_id"] == "request-1"
    assert events[-2] == "lock_exit"
    assert events[-1][0] == "execute"


def test_worker_control_and_shutdown_use_captured_dependencies(monkeypatch):
    manager = SimpleNamespace(
        status=lambda: {"available": True, "busy": False, "queue_depth": 0},
        cancel=lambda job_id: {"success": True, "job_id": job_id},
    )
    shutdown = threading.Event()
    stopped = []
    timers = []

    class Timer:
        def __init__(self, interval, target):
            self.interval = interval
            self.target = target
            self.name = ""
            self.daemon = False
            timers.append(self)

        def start(self):
            return None

    monkeypatch.setattr(worker_ops.threading, "Timer", Timer)
    rpc = _rpc_with_execution(
        worker_manager=manager,
        shutdown_requested=shutdown,
        stop_rpc_server=lambda: stopped.append(True),
    )

    assert rpc.get_worker_status()["available"] is True
    assert rpc.cancel_worker_job("job-7") == {
        "success": True,
        "job_id": "job-7",
    }
    assert rpc.shutdown_rpc_server() == {"success": True, "state": "stopping"}
    assert shutdown.is_set()
    assert len(timers) == 1
    assert timers[0].interval == 0.05
    assert timers[0].target is rpc._execution_collaborators.stop_rpc_server
    assert stopped == []
    assert rpc.shutdown_rpc_server() == {
        "success": True,
        "state": "already_stopping",
    }


def test_gui_execute_resolves_active_document_when_option_omitted(monkeypatch):
    """Omitting document must not skip the native boundary when ActiveDocument exists."""

    api = _CompatibilityAPI()
    recomputes = []

    class Document:
        Name = "ActiveModel"

        def recompute(self):
            recomputes.append(self.Name)

    document = Document()
    freecad = SimpleNamespace(
        ActiveDocument=document,
        getDocument=lambda name: document if name == "ActiveModel" else None,
    )
    rpc = _rpc_with_execution(compatibility_api=api, freecad=freecad)
    monkeypatch.setattr(rpc, "_collect_invalid_objects", dict)
    monkeypatch.setattr(rpc, "_dispatch_gui", lambda task, _timeout: task())
    monkeypatch.setattr(
        execute_code_module,
        "run_execute_code_gui_task",
        lambda *_args, **_kwargs: {
            "ok": True,
            "session": {"saved": False},
            "stdout": "ok",
        },
    )

    result = rpc.execute_code("print('ok')", {"execution_mode": "gui"})

    assert [item[0] for item in api.calls] == ["ActiveModel"]
    assert api.structural_scopes == [True]
    assert recomputes == ["ActiveModel"]
    assert result["success"] is True


def test_gui_execute_without_document_or_active_still_runs_without_boundary(
    monkeypatch,
):
    api = _CompatibilityAPI()
    freecad = SimpleNamespace(ActiveDocument=None, getDocument=lambda _name: None)
    rpc = _rpc_with_execution(compatibility_api=api, freecad=freecad)
    monkeypatch.setattr(rpc, "_collect_invalid_objects", dict)
    monkeypatch.setattr(rpc, "_dispatch_gui", lambda task, _timeout: task())
    monkeypatch.setattr(
        execute_code_module,
        "run_execute_code_gui_task",
        lambda *_args, **_kwargs: {
            "ok": True,
            "session": {},
            "stdout": "pure",
        },
    )

    result = rpc.execute_code("print('pure')", {"execution_mode": "gui"})

    assert api.calls == []
    assert result["success"] is True
    assert "pure" in result["message"]
