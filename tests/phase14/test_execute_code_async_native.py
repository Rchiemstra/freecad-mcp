"""GUI execute_code must await the native owner-thread commit before responding."""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import execute_code as module
from tests.phase14.test_phase14_execute_worker_injection import (
    _ReadinessDocument,
    _real_gui_freecad,
    _rpc_with_execution,
)

pytestmark = pytest.mark.unit


class _DeferredAPI:
    def __init__(self, stage, events, *, native_result=None, wait_error=None):
        self.stage = stage
        self.events = events
        self.native_result = native_result or {"status": "Committed", "committed": True}
        self.wait_error = wait_error

    def commit_compatibility_mutation(self, name, callback, **options):
        assert self.stage[0] == "gui"
        self.events.append("submitted")
        api = self

        class Waiter:
            def await_result(self, timeout):
                assert api.stage[0] == "rpc", "native wait must not block the GUI thread"
                api.events.append("wait")
                if api.wait_error is not None:
                    if callable(api.wait_error):
                        raise api.wait_error()
                    raise api.wait_error
                if api.native_result["status"] != "Committed":
                    return api.native_result
                api.stage[0] = "owner"
                try:
                    callback()
                    if options.get("recompute", True):
                        api.events.append("recompute")
                    postcondition = options.get("postcondition")
                    if postcondition is not None and postcondition() is False:
                        return {"status": "PostconditionFailed", "committed": False}
                    api.events.append("committed")
                    return api.native_result
                finally:
                    api.stage[0] = "rpc"

        return Waiter()


def _setup(monkeypatch, **api_options):
    stage = ["rpc"]
    events = []

    class Document(_ReadinessDocument):
        Modified = False
        FileName = ""

        def __init__(self, name):
            super().__init__()
            self.Name = name

    original = Document("Original")
    target = Document("Target")
    freecad = _real_gui_freecad(original, target, active_document=original)
    freecad.events = events

    def set_active(name):
        assert stage[0] == "gui", "document activation must remain on GUI thread"
        events.append(f"activate:{name}")
        freecad.ActiveDocument = freecad.getDocument(name)

    freecad.setActiveDocument = set_active

    def assert_owner_active():
        assert stage[0] == "owner"
        assert freecad.ActiveDocument is target
        events.append("body")

    freecad.assert_owner_active = assert_owner_active
    api = _DeferredAPI(stage, events, **api_options)
    rpc = _rpc_with_execution(compatibility_api=api, freecad=freecad)
    monkeypatch.setattr(rpc, "_collect_invalid_objects", dict)

    def dispatch(task, timeout, **_kwargs):
        assert stage[0] == "rpc"
        stage[0] = "gui"
        try:
            result = task()
        finally:
            stage[0] = "rpc"
        wait = getattr(result, "await_result", None)
        return wait(timeout) if callable(wait) else result

    monkeypatch.setattr(rpc, "_dispatch_gui", dispatch)

    def flush():
        assert stage[0] == "gui", "GUI delivery must happen after commit on GUI thread"
        events.append("flush")

    monkeypatch.setattr(module, "_flush_gui_events", flush)
    return rpc, freecad, events


def _options(**extra):
    return {
        "document": "Target",
        "execution_mode": "gui",
        "activate_document": True,
        "restore_active_document": True,
        **extra,
    }


@pytest.mark.parametrize("recompute", ["none", "target"])
def test_async_success_waits_for_native_commit_and_preserves_session(monkeypatch, recompute):
    rpc, freecad, events = _setup(monkeypatch)

    result = rpc.execute_code(
        "FreeCAD.assert_owner_active()\nprint('model-created')", _options(recompute=recompute)
    )

    assert result["success"] is True
    assert "model-created" in result["message"]
    assert result["execution"] == {"mode": "gui"}
    assert result["session"]["active_document_before"] == "Original"
    assert result["session"]["active_document_after"] == "Original"
    assert freecad.ActiveDocument.Name == "Original"
    assert events == ["activate:Target", "submitted", "wait", "body"] + (
        ["recompute"] if recompute == "target" else []
    ) + ["committed", "activate:Original", "flush"]


def test_async_body_exception_preserves_actual_error_and_traceback_after_rollback(monkeypatch):
    rpc, freecad, events = _setup(monkeypatch)
    message = "GUI API 'App::DocumentObjectPy::getViewObject' may only be used from the main thread"

    result = rpc.execute_code(
        "FreeCAD.assert_owner_active()\nprint('before-error')\nraise RuntimeError(" + repr(message) + ")",
        _options(recompute="target"),
    )

    assert result["success"] is False
    assert result["error"] == "execute_code failed in document 'Target': " + message
    assert result["traceback"]["exception_type"] == "RuntimeError"
    assert result["traceback"]["message"] == message
    assert "before-error" in result["message"]
    assert result["mutation_readiness"][0]["ready"] is True
    assert result["session"]["active_document_after"] == "Original"
    assert freecad.ActiveDocument.Name == "Original"
    assert events == ["activate:Target", "submitted", "wait", "body", "activate:Original"]


def test_async_native_rejection_exposes_terminal_status_and_reason(monkeypatch):
    rpc, freecad, events = _setup(
        monkeypatch,
        native_result={"status": "Busy", "committed": False, "message": "native commit busy"},
    )

    result = rpc.execute_code("raise AssertionError('must not execute')", _options())

    assert result["success"] is False
    assert result["native_status"] == "Busy"
    assert result["native_message"] == "native commit busy"
    assert freecad.ActiveDocument.Name == "Original"
    assert events == ["activate:Target", "submitted", "wait", "activate:Original"]


def test_async_timeout_does_not_restore_document_while_native_callback_may_still_run(monkeypatch):
    def native_timeout():
        # An unfinished native mutation normally still owns a transaction.
        # That state must never be confused with a completed failed rollback.
        freecad.getDocument("Target")._readiness["pending_transaction"] = True
        return TimeoutError("native wait timed out")

    rpc, freecad, events = _setup(monkeypatch, wait_error=native_timeout)

    with pytest.raises(TimeoutError, match="native wait timed out"):
        rpc.execute_code("pass", _options())

    assert freecad.ActiveDocument.Name == "Target"
    assert module.document_readiness(freecad.getDocument("Target"))["quarantined"] is False
    assert events == ["activate:Target", "submitted", "wait"]
