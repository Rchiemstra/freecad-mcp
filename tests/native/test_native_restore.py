"""Native qualification matrix for ``restore``."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.core


def _require_native_collaboration() -> None:
    if os.environ.get("FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION") != "1":
        pytest.skip("Compose FreeCAD is adapter-only; use the branch-built lane")


from tests.native_model_state import model_state as _model_state

def _collaborators(FreeCAD, validator):
    from addon.FreeCADMCP.collaboration_api import CollaborationAPI

    bridge = CollaborationAPI(document_lookup=FreeCAD.getDocument)
    return SimpleNamespace(
        validate_document_invariants=validator,
        commit_native_mutation=bridge.commit_native_mutation,
        freecad=FreeCAD,
    )


def _close_named(FreeCAD, name: str) -> None:
    try:
        FreeCAD.closeDocument(name)
    except Exception:
        pass


def _documents(FreeCAD) -> dict[str, object]:
    listing = getattr(FreeCAD, "listDocuments", None)
    if not callable(listing):
        return {}
    raw = listing()
    if isinstance(raw, dict):
        return raw
    names = raw if isinstance(raw, (list, tuple)) else ()
    found: dict[str, object] = {}
    getter = getattr(FreeCAD, "getDocument", None)
    if not callable(getter):
        return found
    for name in names:
        if not isinstance(name, str):
            continue
        try:
            found[name] = getter(name)
        except Exception:
            continue
    return found


def _prepare(document):
    if document.getObject('Seed') is None:
        document.addObject('App::FeaturePython', 'Seed')
    body = document.getObject('Body')
    if body is None:
        try:
            body = document.addObject('PartDesign::Body', 'Body')
        except Exception:
            body = document.addObject('App::FeaturePython', 'Body')
    import importlib
    import os
    import tempfile
    handle, path = tempfile.mkstemp(suffix='.FCStd', prefix='mcp_snap_')
    os.close(handle)
    saver = getattr(document, 'saveCopy', None)
    if callable(saver):
        saver(path)
    module = importlib.import_module('FreeCAD')
    snaps = getattr(module, '_mcp_snapshots', None)
    if not isinstance(snaps, list):
        snaps = []
        module._mcp_snapshots = snaps
    snaps.append({'id': 'snap-test', 'path': path, 'doc': document.Name})
    document.recompute()
    return body


class RecomputeProbe:
    # FreeCAD reloads proxies by module/class name. Function-local classes and
    # object references captured before Document.load cannot probe the reload.
    events = []
    failure = None

    def execute(self, _object):
        self.events.append("recompute")
        if self.failure:
            raise RuntimeError(self.failure)


def test_restore_native_success_validates_reloaded_state(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import restore as subject

    document = FreeCAD.newDocument("MCPRestoreNativeSuccess")
    events = []
    monkeypatch.setattr(RecomputeProbe, "events", events)

    probe = document.addObject("App::FeaturePython", "RecomputeProbe")
    probe.Proxy = RecomputeProbe()
    _prepare(document)
    events.clear()
    original_apply = subject.apply_restore
    original_read = subject.read_restore_result

    def tracked_apply(admitted, request):
        events.append("apply")
        return original_apply(admitted, request)

    def tracked_read(admitted, receipt):
        events.append("inspect")
        return original_read(admitted, receipt)

    monkeypatch.setattr(subject, "apply_restore", tracked_apply)
    monkeypatch.setattr(subject, "read_restore_result", tracked_read)
    try:
        result = subject.run_restore(_collaborators(FreeCAD, lambda _d: events.append("validate")), document.Name, "snap-test")
        assert result["success"] is True
        assert events == ["apply", "inspect", "recompute", "validate"]
        assert isinstance(document.getObject("RecomputeProbe").Proxy, RecomputeProbe)
    finally:
        for name in list(_documents(FreeCAD)):
            _close_named(FreeCAD, name)


def test_restore_native_validation_failure_after_load_is_uncertain():
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.restore import run_restore

    document = FreeCAD.newDocument("MCPRestoreNativeRollback")
    _prepare(document)
    state_before = _model_state(document)
    try:
        result = run_restore(
            _collaborators(FreeCAD, lambda _d: (_ for _ in ()).throw(RuntimeError("forced validation failure"))),
            document.Name, "snap-test",
        )
        assert result["success"] is False
        # Loading is a GUI lifecycle operation after native admission. A
        # validation failure cannot prove that the old model was rolled back.
        assert result["error_code"] == "RESTORE_FAILED"
        assert result["outcome"] == "uncertain"
        assert result["committed"] is True
        assert "forced validation failure" in result["error"]
        assert "rollback_succeeded" not in result
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_restore_native_apply_failure_restores(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import restore as subject

    document = FreeCAD.newDocument("MCPRestoreNativeApplyFailure")
    _prepare(document)
    state_before = _model_state(document)
    original = subject.apply_restore

    def mutates_then_raises(admitted, request):
        original(admitted, request)
        admitted.addObject("App::FeaturePython", "TransientSupport")
        raise RuntimeError("forced failure after structural effects")

    monkeypatch.setattr(subject, "apply_restore", mutates_then_raises)
    try:
        result = subject.run_restore(_collaborators(FreeCAD, lambda _d: None), document.Name, "snap-test")
        assert result["success"] is False
        assert result["native_status"] == "ApplyFailed"
        assert document.getObject("TransientSupport") is None
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_restore_native_recompute_failure_after_load_is_uncertain(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.restore import run_restore
    from addon.FreeCADMCP.rpc_server.mutation_guard_ops.validate_invariants import validate_document_invariants

    document = FreeCAD.newDocument("MCPRestoreNativeRecomputeFailure")
    probe = document.addObject("App::FeaturePython", "FailingRecomputeProbe")
    probe.Proxy = RecomputeProbe()
    _prepare(document)
    monkeypatch.setattr(RecomputeProbe, "failure", "forced native recompute failure")
    try:
        result = run_restore(_collaborators(FreeCAD, validate_document_invariants), document.Name, "snap-test")
        assert result["success"] is False
        assert result["outcome"] == "uncertain"
        assert result["error_code"] == "RESTORE_FAILED"
        assert "FailingRecomputeProbe" in result["error"]
        assert "rollback_succeeded" not in result
        assert "Invalid" in document.getObject("FailingRecomputeProbe").State
    finally:
        FreeCAD.closeDocument(document.Name)


def test_restore_native_failed_reload_remains_uncertain_on_retry():
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.restore import run_restore

    document = FreeCAD.newDocument("MCPRestoreNativeReloadFailure")
    _prepare(document)
    calls = []

    def fail_validation(admitted):
        calls.append(admitted)
        raise RuntimeError("persistent post-load validation failure")

    collaborators = _collaborators(FreeCAD, fail_validation)
    try:
        for _ in range(2):
            result = run_restore(collaborators, document.Name, "snap-test")
            assert result["outcome"] == "uncertain"
            assert result["error_code"] == "RESTORE_FAILED"
            assert "persistent post-load validation failure" in result["error"]
            assert "rollback_succeeded" not in result
        assert calls == [document, document]
    finally:
        FreeCAD.closeDocument(document.Name)


def test_restore_native_inspection_failure_rolls_back(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import restore as subject

    document = FreeCAD.newDocument("MCPRestoreNativeInspectionFailure")
    _prepare(document)
    state_before = _model_state(document)

    def reject(_document, _receipt):
        raise subject.RestoreError("CREATED_OBJECT_WRONG_TYPE", "forced inspection failure")

    monkeypatch.setattr(subject, "read_restore_result", reject)
    try:
        result = subject.run_restore(_collaborators(FreeCAD, lambda _d: None), document.Name, "snap-test")
        assert result["success"] is False
        assert result["error_code"] == "CREATED_OBJECT_WRONG_TYPE"
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_restore_native_reloads_snapshot_after_mutation(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.restore import run_restore

    document = FreeCAD.newDocument("MCPRestoreNativeReload")
    _prepare(document)
    document.addObject("App::FeaturePython", "Transient")
    document.recompute()
    doc_name = document.Name
    try:
        result = run_restore(_collaborators(FreeCAD, lambda _d: None), doc_name, "snap-test")
        assert result["success"] is True
        remaining = _documents(FreeCAD)
        assert remaining, "restore close/open left no document"
        assert all(doc.getObject("Transient") is None for doc in remaining.values())
    finally:
        for name in list(_documents(FreeCAD)):
            _close_named(FreeCAD, name)


def test_restore_native_postcondition_cannot_write(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import restore as subject

    document = FreeCAD.newDocument("MCPRestoreReadOnlyPostcondition")
    anchor = document.addObject("App::FeaturePython", "Anchor")
    _prepare(document)
    state_before = _model_state(document)

    original_read = subject.read_restore_result

    def mutate_postcondition(admitted, receipt):
        # Inspection is native/read-only; health validation happens after load.
        anchor.Label = "Unvalidated change"
        return original_read(admitted, receipt)

    monkeypatch.setattr(subject, "read_restore_result", mutate_postcondition)
    try:
        result = subject.run_restore(_collaborators(FreeCAD, lambda _d: None), document.Name, "snap-test")
        assert result["outcome"] == "rejected"
        assert result["native_status"] == "PostconditionFailed"
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_restore_native_validator_cannot_write_reloaded_object():
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.restore import run_restore

    document = FreeCAD.newDocument("MCPRestoreReadOnlyValidator")
    document.addObject("App::FeaturePython", "Anchor")
    _prepare(document)
    loaded_state = _model_state(document)
    document.getObject("Anchor").Label = "Change after snapshot"
    document.addObject("App::FeaturePython", "Transient")
    document.recompute()
    calls = []

    def mutate_validator(admitted):
        # Document.load replaces object proxies: reacquire the loaded object.
        calls.append(admitted.getObject("Anchor").Label)
        admitted.getObject("Anchor").Label = "Unvalidated change"
        return {"ok": True}

    try:
        result = run_restore(_collaborators(FreeCAD, mutate_validator), document.Name, "snap-test")
        assert calls == ["Anchor"]
        assert result["success"] is False
        assert result["error_code"] == "RESTORE_FAILED"
        assert result["outcome"] == "uncertain"
        assert result["committed"] is True
        assert "rollback_succeeded" not in result
        assert _model_state(document) == loaded_state
    finally:
        FreeCAD.closeDocument(document.Name)
