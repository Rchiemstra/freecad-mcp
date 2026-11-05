"""Native qualification matrix for ``restore``."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.core


def _document_has_native_collaboration(document: object) -> bool:
    identity = getattr(document, "collaborationIdentity", None)
    commit = getattr(document, "commitCompatibilityMutation", None)
    if not callable(identity) or not callable(commit):
        return False
    try:
        payload = identity()
    except Exception:
        return False
    return isinstance(payload, dict) and type(payload.get("instance_id")) is int


_NATIVE_COLLABORATION: bool | None = None


def _require_native_collaboration() -> None:
    global _NATIVE_COLLABORATION
    if _NATIVE_COLLABORATION is None:
        import FreeCAD

        probe = FreeCAD.newDocument("MCPNativeCollabProbe")
        try:
            _NATIVE_COLLABORATION = _document_has_native_collaboration(probe)
        finally:
            FreeCAD.closeDocument(probe.Name)
    if not _NATIVE_COLLABORATION:
        pytest.skip(
            "FreeCAD has no collaborationIdentity()/commitCompatibilityMutation()"
        )


def _assert_snapshot_selected(document: object, snapshot_id: str) -> None:
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.restore import (
        apply_restore,
        build_restore_request,
    )

    request = build_restore_request(getattr(document, "Name", None), snapshot_id)
    assert not isinstance(request, dict), request
    receipt = apply_restore(document, request)
    assert str(receipt.name) == snapshot_id


def _assert_snapshot_rejected(document: object, snapshot_id: str | None) -> None:
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.restore import (
        RestoreError,
        apply_restore,
        build_restore_request,
    )

    request = build_restore_request(getattr(document, "Name", None), snapshot_id)
    assert not isinstance(request, dict), request
    with pytest.raises(RestoreError) as caught:
        apply_restore(document, request)
    assert caught.value.code == "SNAPSHOT_NOT_FOUND"


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
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.snapshot_owner import (
        snapshot_owner_fields,
    )

    snaps.append({'id': 'snap-test', 'path': path, 't': 0, **snapshot_owner_fields(document)})
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


def _isolate_snapshot_ring(FreeCAD):
    previous = getattr(FreeCAD, "_mcp_snapshots", None)
    FreeCAD._mcp_snapshots = []
    return previous


def _restore_snapshot_ring(FreeCAD, previous) -> None:
    current = getattr(FreeCAD, "_mcp_snapshots", None)
    if isinstance(current, list):
        for row in current:
            path = row.get("path") if isinstance(row, dict) else None
            if isinstance(path, str):
                try:
                    os.remove(path)
                except OSError:
                    pass
    if isinstance(previous, list):
        FreeCAD._mcp_snapshots = previous
    else:
        FreeCAD._mcp_snapshots = []


def test_restore_native_reused_document_name_does_not_select_previous_snapshot():
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.diagnostics_io_actions import (
        snapshot_document,
    )
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.restore import run_restore
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.snapshot_restore import (
        restore_gui,
    )
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.snapshot_restore_target import (
        resolve_restore_target,
        validate_restore_target,
    )

    previous = _isolate_snapshot_ring(FreeCAD)
    try:
        first = FreeCAD.newDocument("MCPRestoreReuse")
        first.addObject("App::FeaturePython", "Original")
        first.recompute()
        native = _document_has_native_collaboration(first)
        first_uid = str(first.Uid)
        payload = snapshot_document(first)
        snap_id = str(payload["snapshot_id"])
        row = FreeCAD._mcp_snapshots[-1]
        assert row["document_uid"] == first_uid
        if native:
            assert row["document_instance_id"] == first.collaborationIdentity()["instance_id"]
        else:
            assert isinstance(row.get("document_owner_token"), str)
            assert row["document_owner_token"]
            assert "document_instance_id" not in row
        _assert_snapshot_selected(first, snap_id)
        if not native:
            first.addObject("App::FeaturePython", "Extra")
            first.recompute()
            restore_gui(None, first.Name, snap_id)
            live = FreeCAD.getDocument(first.Name)
            assert live.getObject("Extra") is None
            assert live.getObject("Original") is not None
        FreeCAD.closeDocument(first.Name)

        second = FreeCAD.newDocument("MCPRestoreReuse")
        second.addObject("App::FeaturePython", "Successor")
        second.recompute()
        assert second.Name == "MCPRestoreReuse"
        assert str(second.Uid) != first_uid
        _assert_snapshot_rejected(second, snap_id)
        _assert_snapshot_rejected(second, None)
        if native:
            result = run_restore(
                _collaborators(FreeCAD, lambda _document: None),
                second.Name,
                snap_id,
            )
            assert result["success"] is False
            assert result["error_code"] == "SNAPSHOT_NOT_FOUND"
            omitted = run_restore(
                _collaborators(FreeCAD, lambda _document: None),
                second.Name,
                None,
            )
            assert omitted["success"] is False
            assert omitted["error_code"] == "SNAPSHOT_NOT_FOUND"
        else:
            rejected = restore_gui(None, second.Name, snap_id)
            assert rejected["error_code"] == "SNAPSHOT_DOCUMENT_MISMATCH"
        assert second.getObject("Successor") is not None
        assert second.getObject("Original") is None

        target, error = resolve_restore_target(second, snap_id)
        assert error is None and target is not None
        mismatch = validate_restore_target(target, second)
        assert mismatch is not None
        assert mismatch["error_code"] == "SNAPSHOT_DOCUMENT_MISMATCH"
        missing, missing_error = resolve_restore_target(second, None)
        assert missing is None
        assert missing_error is not None
        assert missing_error["error_code"] == "SNAPSHOT_DOCUMENT_MISMATCH"
    finally:
        for name in list(_documents(FreeCAD)):
            _close_named(FreeCAD, name)
        _restore_snapshot_ring(FreeCAD, previous)


def test_restore_native_opened_copy_keeps_its_own_snapshot():
    import tempfile

    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.diagnostics_io_actions import (
        snapshot_document,
    )
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.restore import run_restore
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.snapshot_owner import (
        row_belongs_to_document,
    )
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.snapshot_restore import (
        restore_gui,
    )

    previous = _isolate_snapshot_ring(FreeCAD)
    copy_path = ""
    try:
        source = FreeCAD.newDocument("MCPRestoreSource")
        source.addObject("App::FeaturePython", "Original")
        source.recompute()
        native = _document_has_native_collaboration(source)
        payload = snapshot_document(source)
        snap_id = str(payload["snapshot_id"])
        handle, copy_path = tempfile.mkstemp(suffix=".FCStd")
        os.close(handle)
        source.saveCopy(copy_path)
        opened = FreeCAD.openDocument(copy_path)
        assert opened is not source
        assert str(opened.Uid) == str(source.Uid)
        row = FreeCAD._mcp_snapshots[-1]
        if native:
            assert (
                opened.collaborationIdentity()["instance_id"]
                != source.collaborationIdentity()["instance_id"]
            )
        else:
            assert row_belongs_to_document(row, opened) is False
            assert row_belongs_to_document(row, source) is True
        _assert_snapshot_rejected(opened, snap_id)
        _assert_snapshot_selected(source, snap_id)

        if native:
            rejected = run_restore(
                _collaborators(FreeCAD, lambda _document: None),
                opened.Name,
                snap_id,
            )
            assert rejected["success"] is False
            assert rejected["error_code"] == "SNAPSHOT_NOT_FOUND"
            restored = run_restore(
                _collaborators(FreeCAD, lambda _document: None),
                source.Name,
                snap_id,
            )
            assert restored["success"] is True
            assert source.getObject("Original") is not None
        else:
            source.addObject("App::FeaturePython", "Extra")
            source.recompute()
            restore_gui(None, source.Name, snap_id)
            live = FreeCAD.getDocument(source.Name)
            assert live.getObject("Extra") is None
            assert live.getObject("Original") is not None
            rejected_gui = restore_gui(None, opened.Name, snap_id)
            assert rejected_gui["error_code"] == "SNAPSHOT_DOCUMENT_MISMATCH"
            assert opened.getObject("Original") is not None
    finally:
        for name in list(_documents(FreeCAD)):
            _close_named(FreeCAD, name)
        if copy_path:
            try:
                os.remove(copy_path)
            except OSError:
                pass
        _restore_snapshot_ring(FreeCAD, previous)
