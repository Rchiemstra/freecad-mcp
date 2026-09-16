"""Native qualification matrix for ``validate_movement_follow``."""

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
    )


def _prepare(document):
    if document.getObject('Seed') is None:
        document.addObject('App::FeaturePython', 'Seed')
    if document.getObject('Target') is None:
        document.addObject('App::FeaturePython', 'Target')
    body = document.getObject('Body')
    if body is None:
        try:
            body = document.addObject('PartDesign::Body', 'Body')
        except Exception:
            body = document.addObject('App::FeaturePython', 'Body')
    document.recompute()
    return body


def test_validate_movement_follow_native_success_inspects_after_recompute(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import validate_movement_follow as subject

    document = FreeCAD.newDocument("MCPValidateMovementFollowNativeSuccess")
    events = []

    class RecomputeProbe:
        def execute(self, _object):
            events.append("recompute")

    probe = document.addObject("App::FeaturePython", "RecomputeProbe")
    probe.Proxy = RecomputeProbe()
    _prepare(document)
    events.clear()
    original_apply = subject.apply_validate_movement_follow
    original_read = subject.read_validate_movement_follow_result

    def tracked_apply(admitted, request):
        events.append("apply")
        probe.touch()
        return original_apply(admitted, request)

    def tracked_read(admitted, receipt):
        events.append("inspect")
        return original_read(admitted, receipt)

    monkeypatch.setattr(subject, "apply_validate_movement_follow", tracked_apply)
    monkeypatch.setattr(subject, "read_validate_movement_follow_result", tracked_read)
    try:
        result = subject.run_validate_movement_follow(_collaborators(FreeCAD, lambda _d: events.append("validate")), document.Name, "Seed", ["Seed"], [0, 0, 1], [0, 0, 1], 90.0, True, 1e-07)
        assert result["success"] is True
        assert events == ["apply", "recompute", "inspect", "validate"]
    finally:
        FreeCAD.closeDocument(document.Name)


def test_validate_movement_follow_native_validation_failure_restores_complete_state():
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.validate_movement_follow import run_validate_movement_follow

    document = FreeCAD.newDocument("MCPValidateMovementFollowNativeRollback")
    _prepare(document)
    state_before = _model_state(document)
    try:
        result = run_validate_movement_follow(
            _collaborators(FreeCAD, lambda _d: (_ for _ in ()).throw(RuntimeError("forced validation failure"))),
            document.Name, "Seed", ["Seed"], [0, 0, 1], [0, 0, 1], 90.0, True, 1e-07,
        )
        assert result["success"] is False
        assert result["error_code"] == "DOCUMENT_HEALTH_DEGRADED"
        assert result["rollback_succeeded"] is True
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_validate_movement_follow_native_apply_failure_restores(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import validate_movement_follow as subject

    document = FreeCAD.newDocument("MCPValidateMovementFollowNativeApplyFailure")
    _prepare(document)
    state_before = _model_state(document)
    original = subject.apply_validate_movement_follow

    def mutates_then_raises(admitted, request):
        original(admitted, request)
        admitted.addObject("App::FeaturePython", "TransientSupport")
        raise RuntimeError("forced failure after structural effects")

    monkeypatch.setattr(subject, "apply_validate_movement_follow", mutates_then_raises)
    try:
        result = subject.run_validate_movement_follow(_collaborators(FreeCAD, lambda _d: None), document.Name, "Seed", ["Seed"], [0, 0, 1], [0, 0, 1], 90.0, True, 1e-07)
        assert result["success"] is False
        assert result["native_status"] == "ApplyFailed"
        assert document.getObject("TransientSupport") is None
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_validate_movement_follow_native_recompute_failure_rolls_back(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import validate_movement_follow as subject

    document = FreeCAD.newDocument("MCPValidateMovementFollowNativeRecomputeFailure")

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
    original = subject.apply_validate_movement_follow

    def arm(admitted, request):
        receipt = original(admitted, request)
        proxy.armed = True
        probe.touch()
        return receipt

    monkeypatch.setattr(subject, "apply_validate_movement_follow", arm)
    try:
        result = subject.run_validate_movement_follow(_collaborators(FreeCAD, lambda _d: None), document.Name, "Seed", ["Seed"], [0, 0, 1], [0, 0, 1], 90.0, True, 1e-07)
        assert result["success"] is False
        assert result["native_status"] == "RecomputeFailed"
        assert _model_state(document) == state_before
    finally:
        proxy.armed = False
        FreeCAD.closeDocument(document.Name)


def test_validate_movement_follow_native_rollback_failure_is_uncertain_and_fences(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import validate_movement_follow as subject

    document = FreeCAD.newDocument("MCPValidateMovementFollowNativeRollbackFailure")

    class PersistentFailureProbe:
        armed = False

        def execute(self, _object):
            if self.armed:
                raise RuntimeError("persistent recompute failure blocks restoration")

    proxy = PersistentFailureProbe()
    probe = document.addObject("App::FeaturePython", "PersistentFailureProbe")
    probe.Proxy = proxy
    _prepare(document)
    original = subject.apply_validate_movement_follow

    def arm(admitted, request):
        receipt = original(admitted, request)
        proxy.armed = True
        probe.touch()
        return receipt

    monkeypatch.setattr(subject, "apply_validate_movement_follow", arm)
    collaborators = _collaborators(FreeCAD, lambda _d: None)
    try:
        result = subject.run_validate_movement_follow(collaborators, document.Name, "Seed", ["Seed"], [0, 0, 1], [0, 0, 1], 90.0, True, 1e-07)
        proxy.armed = False
        fenced = subject.run_validate_movement_follow(collaborators, document.Name, "Seed", ["Seed"], [0, 0, 1], [0, 0, 1], 90.0, True, 1e-07)
        assert result["outcome"] == "uncertain"
        assert fenced["success"] is False
    finally:
        proxy.armed = False
        FreeCAD.closeDocument(document.Name)


def test_validate_movement_follow_native_inspection_failure_rolls_back(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import validate_movement_follow as subject

    document = FreeCAD.newDocument("MCPValidateMovementFollowNativeInspectionFailure")
    _prepare(document)
    state_before = _model_state(document)

    def reject(_document, _receipt):
        raise subject.ValidateMovementFollowError("CREATED_OBJECT_WRONG_TYPE", "forced inspection failure")

    monkeypatch.setattr(subject, "read_validate_movement_follow_result", reject)
    try:
        result = subject.run_validate_movement_follow(_collaborators(FreeCAD, lambda _d: None), document.Name, "Seed", ["Seed"], [0, 0, 1], [0, 0, 1], 90.0, True, 1e-07)
        assert result["success"] is False
        assert result["error_code"] == "CREATED_OBJECT_WRONG_TYPE"
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_validate_movement_follow_native_postcondition_cannot_write():
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.validate_movement_follow import run_validate_movement_follow

    document = FreeCAD.newDocument("MCPValidateMovementFollowReadOnlyPostcondition")
    anchor = document.addObject("App::FeaturePython", "Anchor")
    _prepare(document)
    state_before = _model_state(document)

    def validate(_admitted):
        anchor.Label = "Unvalidated change"

    try:
        result = run_validate_movement_follow(_collaborators(FreeCAD, validate), document.Name, "Seed", ["Seed"], [0, 0, 1], [0, 0, 1], 90.0, True, 1e-07)
        assert result["outcome"] == "rejected"
        assert result["native_status"] == "PostconditionFailed"
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)
