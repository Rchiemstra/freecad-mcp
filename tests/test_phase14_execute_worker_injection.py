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
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_gui_task import (
    NATIVE_POST_RECOMPUTE_MARKER,
    run_execute_code_gui_task,
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
    def __init__(
        self,
        *,
        invoke_callback: bool = True,
        native_result=None,
        native_recompute=None,
    ) -> None:
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
        self.recompute_policies = []
        self.postcondition_scopes = []
        self.native_recompute = native_recompute

    def commit_compatibility_mutation(
        self,
        document_name,
        callback,
        *,
        structural=False,
        recompute=True,
        postcondition=None,
    ):
        self.calls.append((document_name, callback))
        self.structural_scopes.append(structural)
        self.recompute_policies.append(recompute)
        self.postcondition_scopes.append(postcondition is not None)
        if not self.invoke_callback:
            return {"status": "Rejected", "committed": False}
        try:
            result = callback()
        except Exception:
            self.callback_failures += 1
            raise
        self.callback_results.append(result)
        if recompute and callable(self.native_recompute):
            self.native_recompute()
        if postcondition is not None and postcondition() is False:
            return {"status": "PostconditionFailed", "committed": False}
        return self.native_result


class _ReadinessDocument:
    Name = "Model"

    def __init__(self) -> None:
        self._readiness = {
            "ready": True,
            "stable_event_supported": True,
            "pending_transaction": False,
            "booked_transaction": 0,
            "transaction_locked": False,
            "recomputing": False,
            "must_execute": False,
            "pending_removal": False,
            "commit_barrier": False,
            "notification_replay": False,
            "poisoned": False,
            "quarantined": False,
            "diagnostic": "",
        }

    def getMutationReadiness(self):
        return dict(self._readiness)

    def recompute(self):
        return None


def _freecad_with_document(document):
    return SimpleNamespace(
        ActiveDocument=document,
        getDocument=lambda name: document if name == document.Name else None,
    )


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
    paths = [*sorted(EXECUTE_DIR.glob("execute_code*.py")), WORKER_OPS]
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
    assert api.recompute_policies == [False]
    assert api.postcondition_scopes == [False]
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
    document = _ReadinessDocument()
    rpc = _rpc_with_execution(
        compatibility_api=api,
        freecad=_freecad_with_document(document),
    )
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
    assert result["error"] == (
        "Native compatibility mutation rejected execution in document 'Model' (Rejected)"
    )
    assert result["error_code"] == "NATIVE_COMPATIBILITY_MUTATION_REJECTED"
    assert result["native_status"] == "Rejected"
    assert result["mutation_readiness"][0]["ready"] is True
    assert result["retryable"] is True


def test_native_rejection_after_callback_fails_closed_in_execute_envelope(
    monkeypatch,
):
    api = _CompatibilityAPI(
        native_result={"status": "PostconditionFailed", "committed": False}
    )
    document = _ReadinessDocument()
    rpc = _rpc_with_execution(
        compatibility_api=api,
        freecad=_freecad_with_document(document),
    )
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
        "Native compatibility mutation rejected execution in document 'Model' "
        "(PostconditionFailed)"
    )
    assert result["error_code"] == "NATIVE_COMPATIBILITY_MUTATION_REJECTED"
    assert result["native_status"] == "PostconditionFailed"
    assert result["mutation_readiness"][0]["ready"] is True
    assert result["retryable"] is True


def test_late_native_busy_reports_healthy_retryable_readiness(monkeypatch):
    document = _ReadinessDocument()
    api = _CompatibilityAPI(
        native_result={
            "status": "Busy",
            "committed": False,
            "message": "commit admission changed before the transaction opened",
        }
    )
    rpc = _rpc_with_execution(
        compatibility_api=api,
        freecad=_freecad_with_document(document),
    )
    monkeypatch.setattr(rpc, "_collect_invalid_objects", dict)
    monkeypatch.setattr(rpc, "_dispatch_gui", lambda task, _timeout: task())
    monkeypatch.setattr(
        execute_code_module,
        "run_execute_code_gui_task",
        lambda *_args, **_kwargs: {"ok": True, "session": {}, "stdout": "hidden"},
    )

    result = rpc.execute_code(
        "print('hidden')",
        {"document": document.Name, "execution_mode": "gui"},
    )

    assert result["error_code"] == "NATIVE_COMPATIBILITY_MUTATION_REJECTED"
    assert result["native_status"] == "Busy"
    assert result["native_message"] == (
        "commit admission changed before the transaction opened"
    )
    assert result["mutation_readiness"][0]["ready"] is True
    assert result["retryable"] is True


def test_gui_error_requests_native_rollback_and_preserves_error_envelope(monkeypatch):
    api = _CompatibilityAPI()
    document = _ReadinessDocument()
    rpc = _rpc_with_execution(
        compatibility_api=api,
        freecad=_freecad_with_document(document),
    )
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
    assert result["error"] == (
        "execute_code failed in document 'Model': historical execute failure"
    )
    assert result["document_name"] == "Model"
    assert result["traceback"] == "traceback-contract"
    assert result["session"] == {"saved": False}
    assert result["message"] == "partial output"
    assert result["mutation_readiness"][0]["ready"] is True
    assert result["retryable"] is True


def test_native_rollback_rejection_quarantines_execute_document(monkeypatch):
    document = _ReadinessDocument()
    api = _CompatibilityAPI(
        native_result={
            "status": "RollbackFailed",
            "committed": False,
            "rollback_succeeded": False,
            "message": "rollback could not restore the transaction",
        },
    )
    rpc = _rpc_with_execution(
        compatibility_api=api,
        freecad=_freecad_with_document(document),
    )
    monkeypatch.setattr(rpc, "_collect_invalid_objects", dict)
    monkeypatch.setattr(rpc, "_dispatch_gui", lambda task, _timeout: task())
    monkeypatch.setattr(
        execute_code_module,
        "run_execute_code_gui_task",
        lambda *_args, **_kwargs: {"ok": True, "session": {}, "stdout": "hidden"},
    )

    result = rpc.execute_code(
        "print('must not run')",
        {"document": document.Name, "execution_mode": "gui"},
    )

    assert result["error_code"] == "NATIVE_COMPATIBILITY_MUTATION_REJECTED"
    assert result["native_status"] == "RollbackFailed"
    assert result["rollback_succeeded"] is False
    assert result["native_message"] == "rollback could not restore the transaction"
    assert result["mutation_readiness"][0]["quarantined"] is True
    assert result["retryable"] is False


def test_native_rollback_exception_is_structured_and_quarantined(monkeypatch):
    document = _ReadinessDocument()

    class RollbackFailureAPI:
        def commit_compatibility_mutation(
            self,
            _document_name,
            callback,
            *,
            structural=False,
            recompute=True,
            postcondition=None,
        ):
            assert structural is True
            assert recompute is False
            assert postcondition is None
            callback()
            document._readiness.update(
                ready=False,
                poisoned=True,
                diagnostic="rollback restore failed",
            )
            raise RuntimeError("rollback restore failed")

    rpc = _rpc_with_execution(
        compatibility_api=RollbackFailureAPI(),
        freecad=_freecad_with_document(document),
    )
    monkeypatch.setattr(rpc, "_collect_invalid_objects", dict)
    monkeypatch.setattr(rpc, "_dispatch_gui", lambda task, _timeout: task())
    monkeypatch.setattr(
        execute_code_module,
        "run_execute_code_gui_task",
        lambda *_args, **_kwargs: {"ok": True, "session": {}, "stdout": "hidden"},
    )

    result = rpc.execute_code(
        "print('hidden')",
        {"document": document.Name, "execution_mode": "gui"},
    )

    assert result["error_code"] == "TRANSACTION_ROLLBACK_FAILED"
    assert result["diagnostic"] == "rollback restore failed"
    assert result["mutation_readiness"][0]["quarantined"] is True
    assert result["mutation_readiness"][0]["collaboration_poisoned"] is True
    assert result["retryable"] is False


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

    class Document(_ReadinessDocument):
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
    assert api.recompute_policies == [False]
    assert api.postcondition_scopes == [False]
    assert recomputes == []
    assert result["success"] is True


def test_gui_execute_settles_pending_recompute_before_native_boundary(monkeypatch):
    """Generated mutations retry a healthy pending-recompute admission state."""

    api = _CompatibilityAPI()
    events = []

    class Document:
        Name = "PendingModel"

        def __init__(self):
            self.pending = True

        def getMutationReadiness(self):
            return {
                "ready": not self.pending,
                "stable_event_supported": True,
                "pending_transaction": False,
                "booked_transaction": 0,
                "transaction_locked": False,
                "recomputing": False,
                "must_execute": self.pending,
                "pending_removal": False,
                "commit_barrier": False,
                "notification_replay": False,
                "poisoned": False,
                "quarantined": False,
                "diagnostic": "Pending recompute" if self.pending else "",
            }

        def recompute(self):
            events.append("recompute")
            self.pending = False

    document = Document()
    freecad = SimpleNamespace(
        ActiveDocument=document,
        getDocument=lambda name: document if name == document.Name else None,
    )
    rpc = _rpc_with_execution(compatibility_api=api, freecad=freecad)
    monkeypatch.setattr(rpc, "_collect_invalid_objects", dict)
    monkeypatch.setattr(rpc, "_dispatch_gui", lambda task, _timeout: task())
    monkeypatch.setattr(
        execute_code_module,
        "run_execute_code_gui_task",
        lambda *_args, **_kwargs: (
            events.append("callback")
            or {"ok": True, "session": {}, "stdout": "settled"}
        ),
    )

    result = rpc.execute_code(
        "print('settled')",
        {"document": document.Name, "execution_mode": "gui"},
    )

    assert events == ["recompute", "callback"]
    assert [item[0] for item in api.calls] == [document.Name]
    assert api.recompute_policies == [False]
    assert result["success"] is True
    assert "settled" in result["message"]


def test_gui_execute_target_recompute_is_owned_once_by_native_coordinator(
    monkeypatch,
):
    events = []

    class Document(_ReadinessDocument):
        def recompute(self):
            events.append("native-recompute")

    document = Document()
    api = _CompatibilityAPI(native_recompute=document.recompute)
    rpc = _rpc_with_execution(
        compatibility_api=api,
        freecad=_freecad_with_document(document),
    )
    monkeypatch.setattr(rpc, "_collect_invalid_objects", dict)
    monkeypatch.setattr(rpc, "_dispatch_gui", lambda task, _timeout: task())
    monkeypatch.setattr(
        execute_code_module,
        "run_execute_code_gui_task",
        lambda *_args, **_kwargs: (
            events.append("apply")
            or {"ok": True, "session": {}, "stdout": "native-owned"}
        ),
    )
    monkeypatch.setattr(execute_code_module, "_flush_gui_events", lambda: None)

    result = rpc.execute_code(
        "print('native-owned')",
        {
            "document": document.Name,
            "execution_mode": "gui",
            "recompute": "target",
        },
    )

    assert events == ["apply", "native-recompute"]
    assert api.recompute_policies == [True]
    assert api.postcondition_scopes == [True]
    assert result["success"] is True


def test_signed_generated_continuation_runs_after_the_one_native_recompute(
    monkeypatch,
):
    events = []

    class Document(_ReadinessDocument):
        Modified = False
        FileName = ""

        def recompute(self):
            events.append("native-recompute")

    document = Document()
    freecad = SimpleNamespace(
        ActiveDocument=document,
        Console=SimpleNamespace(PrintMessage=lambda _message: None, PrintError=lambda _message: None),
        events=events,
        getDocument=lambda name: document if name == document.Name else None,
        listDocuments=lambda: {document.Name: document},
    )
    api = _CompatibilityAPI(native_recompute=document.recompute)
    rpc = _rpc_with_execution(compatibility_api=api, freecad=freecad)
    monkeypatch.setattr(rpc, "_collect_invalid_objects", dict)
    monkeypatch.setattr(rpc, "_dispatch_gui", lambda task, _timeout: task())
    monkeypatch.setattr(execute_code_module, "_flush_gui_events", lambda: None)

    result = rpc.execute_code(
        "FreeCAD.events.append('apply')\n"
        + NATIVE_POST_RECOMPUTE_MARKER
        + "\nFreeCAD.events.append('postcondition')\nprint('settled')",
        {
            "document": document.Name,
            "execution_mode": "gui",
            "recompute": "target",
            "generated_operation": True,
            "operation_id": "marker-order-test",
        },
    )

    assert events == ["apply", "native-recompute", "postcondition"]
    assert api.recompute_policies == [True]
    assert api.postcondition_scopes == [True]
    assert result["success"] is True
    assert "settled" in result["message"]


def test_generated_post_recompute_failure_preserves_precise_error_after_rollback(
    monkeypatch,
):
    events = []

    class Document(_ReadinessDocument):
        Modified = False
        FileName = ""

        def recompute(self):
            events.append("native-recompute")

    document = Document()
    freecad = SimpleNamespace(
        ActiveDocument=document,
        Console=SimpleNamespace(PrintMessage=lambda _message: None, PrintError=lambda _message: None),
        events=events,
        getDocument=lambda name: document if name == document.Name else None,
        listDocuments=lambda: {document.Name: document},
    )
    api = _CompatibilityAPI(native_recompute=document.recompute)
    rpc = _rpc_with_execution(compatibility_api=api, freecad=freecad)
    monkeypatch.setattr(rpc, "_collect_invalid_objects", dict)
    monkeypatch.setattr(rpc, "_dispatch_gui", lambda task, _timeout: task())

    result = rpc.execute_code(
        "FreeCAD.events.append('apply')\n"
        + NATIVE_POST_RECOMPUTE_MARKER
        + "\nraise RuntimeError('postcondition rejected')",
        {
            "document": document.Name,
            "execution_mode": "gui",
            "recompute": "target",
            "generated_operation": True,
            "operation_id": "marker-failure-test",
        },
    )

    assert events == ["apply", "native-recompute"]
    assert result["success"] is False
    assert result["error"] == (
        "execute_code failed in document 'Model': postcondition rejected"
    )
    assert result["mutation_readiness"][0]["ready"] is True
    assert result["retryable"] is True


def test_public_execute_cannot_inject_native_post_recompute_continuation():
    result = run_execute_code_gui_task(
        "print('apply')\n"
        + NATIVE_POST_RECOMPUTE_MARKER
        + "\nprint('postcondition')",
        {"document": "Model", "recompute": "target"},
        freecad=SimpleNamespace(),
        native_boundary=True,
        postcondition_sink={},
    )

    assert result["ok"] is False
    assert result["error"] == (
        "native postcondition markers require a signed generated operation"
    )


def test_gui_execute_rejects_multi_document_recompute_before_callback(monkeypatch):
    document = _ReadinessDocument()
    api = _CompatibilityAPI()
    rpc = _rpc_with_execution(
        compatibility_api=api,
        freecad=_freecad_with_document(document),
    )
    monkeypatch.setattr(
        execute_code_module,
        "run_execute_code_gui_task",
        lambda *_args, **_kwargs: pytest.fail("unsupported recompute callback ran"),
    )

    result = rpc.execute_code(
        "print('must not run')",
        {
            "document": document.Name,
            "execution_mode": "gui",
            "recompute": "all",
        },
    )

    assert api.calls == []
    assert result["success"] is False
    assert result["error_code"] == "UNSUPPORTED_NATIVE_RECOMPUTE_SCOPE"
    assert result["retryable"] is False


def test_gui_execute_rejects_non_transient_readiness_without_native_callback(
    monkeypatch,
):
    api = _CompatibilityAPI()

    class Document:
        Name = "BusyModel"

        def getMutationReadiness(self):
            return {
                "ready": False,
                "stable_event_supported": True,
                "pending_transaction": True,
                "booked_transaction": 7,
                "transaction_locked": False,
                "recomputing": False,
                "must_execute": False,
                "pending_removal": False,
                "commit_barrier": False,
                "notification_replay": False,
                "poisoned": False,
                "quarantined": False,
                "diagnostic": "A document transaction is active",
            }

        def recompute(self):
            raise AssertionError("an active transaction must not be waited through")

    document = Document()
    freecad = SimpleNamespace(
        ActiveDocument=document,
        getDocument=lambda name: document if name == document.Name else None,
    )
    rpc = _rpc_with_execution(compatibility_api=api, freecad=freecad)
    monkeypatch.setattr(rpc, "_collect_invalid_objects", dict)
    monkeypatch.setattr(rpc, "_dispatch_gui", lambda task, _timeout: task())
    monkeypatch.setattr(
        execute_code_module,
        "run_execute_code_gui_task",
        lambda *_args, **_kwargs: pytest.fail("blocked mutation callback ran"),
    )

    result = rpc.execute_code(
        "print('must not run')",
        {"document": document.Name, "execution_mode": "gui"},
    )

    assert api.calls == []
    assert result["success"] is False
    assert result["error_code"] == "MUTATION_NOT_READY"
    assert result["waited_for_readiness"] is False
    assert result["mutation_readiness"][0]["reasons"] == [
        "native_transaction_in_progress",
        "native_not_ready",
    ]


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
