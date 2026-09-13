"""Native qualification matrix for ``restore``."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.core


def _require_native() -> None:
    if os.environ.get("FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION") != "1":
        raise RuntimeError("Native qualification requires FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION=1")


def _model_state(document):
    import hashlib

    return tuple(
        (
            item.Name,
            item.TypeId,
            tuple(item.State),
            tuple(sorted(obj.Name for obj in item.InList)),
            tuple(sorted(obj.Name for obj in item.OutList)),
            tuple(
                (
                    name,
                    item.getTypeIdOfProperty(name),
                    item.getGroupOfProperty(name),
                    tuple(item.getPropertyStatus(name)),
                    id(item.Proxy)
                    if name == "Proxy"
                    else hashlib.sha256(bytes(item.dumpPropertyContent(name, 0))).hexdigest(),
                )
                for name in sorted(item.PropertiesList)
            ),
        )
        for item in document.Objects
    )


def _collaborators(FreeCAD, validator):
    from addon.FreeCADMCP.collaboration_api import CollaborationAPI

    bridge = CollaborationAPI(document_lookup=FreeCAD.getDocument)
    return SimpleNamespace(
        validate_document_invariants=validator,
        commit_native_mutation=bridge.commit_native_mutation,
        run_fem_analysis=lambda *_a, **_k: {"success": True, "analysis_name": "Analysis"},
    )


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


def test_restore_native_success_inspects_after_recompute(monkeypatch):
    _require_native()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import restore as subject

    document = FreeCAD.newDocument("MCPRestoreNativeSuccess")
    events = []

    class RecomputeProbe:
        def execute(self, _object):
            events.append("recompute")

    probe = document.addObject("App::FeaturePython", "RecomputeProbe")
    probe.Proxy = RecomputeProbe()
    _prepare(document)
    events.clear()
    original_apply = subject.apply_restore
    original_read = subject.read_restore_result

    def tracked_apply(admitted, request):
        events.append("apply")
        probe.touch()
        return original_apply(admitted, request)

    def tracked_read(admitted, receipt):
        events.append("inspect")
        return original_read(admitted, receipt)

    monkeypatch.setattr(subject, "apply_restore", tracked_apply)
    monkeypatch.setattr(subject, "read_restore_result", tracked_read)
    try:
        result = subject.run_restore(_collaborators(FreeCAD, lambda _d: events.append("validate")), document.Name, "snap-test")
        assert result["success"] is True
        assert events == ["apply", "recompute", "inspect", "validate"]
    finally:
        FreeCAD.closeDocument(document.Name)


def test_restore_native_validation_failure_restores_complete_state():
    _require_native()
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
        assert result["error_code"] == "DOCUMENT_HEALTH_DEGRADED"
        assert result["rollback_succeeded"] is True
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_restore_native_apply_failure_restores(monkeypatch):
    _require_native()
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


def test_restore_native_recompute_failure_rolls_back(monkeypatch):
    _require_native()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import restore as subject

    document = FreeCAD.newDocument("MCPRestoreNativeRecomputeFailure")

    class FailingRecomputeProbe:
        armed = False

        def execute(self, _object):
            if self.armed:
                self.armed = False
                raise RuntimeError("forced native recompute failure")

    proxy = FailingRecomputeProbe()
    probe = document.addObject("App::FeaturePython", "FailingRecomputeProbe")
    probe.Proxy = proxy
    _prepare(document)
    state_before = _model_state(document)
    original = subject.apply_restore

    def arm(admitted, request):
        receipt = original(admitted, request)
        proxy.armed = True
        probe.touch()
        return receipt

    monkeypatch.setattr(subject, "apply_restore", arm)
    try:
        result = subject.run_restore(_collaborators(FreeCAD, lambda _d: None), document.Name, "snap-test")
        assert result["success"] is False
        assert result["native_status"] == "RecomputeFailed"
        assert _model_state(document) == state_before
    finally:
        proxy.armed = False
        FreeCAD.closeDocument(document.Name)


def test_restore_native_rollback_failure_is_uncertain_and_fences(monkeypatch):
    _require_native()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import restore as subject

    document = FreeCAD.newDocument("MCPRestoreNativeRollbackFailure")

    class PersistentFailureProbe:
        armed = False

        def execute(self, _object):
            if self.armed:
                raise RuntimeError("persistent recompute failure blocks restoration")

    proxy = PersistentFailureProbe()
    probe = document.addObject("App::FeaturePython", "PersistentFailureProbe")
    probe.Proxy = proxy
    _prepare(document)
    original = subject.apply_restore

    def arm(admitted, request):
        receipt = original(admitted, request)
        proxy.armed = True
        probe.touch()
        return receipt

    monkeypatch.setattr(subject, "apply_restore", arm)
    collaborators = _collaborators(FreeCAD, lambda _d: None)
    try:
        result = subject.run_restore(collaborators, document.Name, "snap-test")
        proxy.armed = False
        fenced = subject.run_restore(collaborators, document.Name, "snap-test")
        assert result["outcome"] == "uncertain" or result["success"] is False
        assert fenced["success"] is False
    finally:
        proxy.armed = False
        FreeCAD.closeDocument(document.Name)


def test_restore_native_inspection_failure_rolls_back(monkeypatch):
    _require_native()
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


def test_restore_native_postcondition_cannot_write():
    _require_native()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.restore import run_restore

    document = FreeCAD.newDocument("MCPRestoreReadOnlyPostcondition")
    anchor = document.addObject("App::FeaturePython", "Anchor")
    _prepare(document)
    state_before = _model_state(document)

    def validate(_admitted):
        anchor.Label = "Unvalidated change"

    try:
        result = run_restore(_collaborators(FreeCAD, validate), document.Name, "snap-test")
        assert result["outcome"] == "rejected"
        assert result["native_status"] == "PostconditionFailed"
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)
