"""Native qualification matrix for ``build_path_wire``."""

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
    import Part

    if document.getObject("Seed") is None:
        line = Part.makeLine((0, 0, 0), (10, 0, 0))
        seed = document.addObject("Part::Feature", "Seed")
        seed.Shape = Part.Wire([line])
    body = document.getObject("Body")
    if body is None:
        body = document.addObject("PartDesign::Body", "Body")
    document.recompute()
    return body


def test_build_path_wire_native_success_inspects_after_recompute(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import build_path_wire as subject

    document = FreeCAD.newDocument("MCPBuildPathWireNativeSuccess")
    events = []

    class RecomputeProbe:
        def execute(self, _object):
            events.append("recompute")

    probe = document.addObject("App::FeaturePython", "RecomputeProbe")
    probe.Proxy = RecomputeProbe()
    _prepare(document)
    events.clear()
    original_apply = subject.apply_build_path_wire
    original_read = subject.read_build_path_wire_result

    def tracked_apply(admitted, request):
        events.append("apply")
        probe.touch()
        return original_apply(admitted, request)

    def tracked_read(admitted, receipt):
        events.append("inspect")
        return original_read(admitted, receipt)

    monkeypatch.setattr(subject, "apply_build_path_wire", tracked_apply)
    monkeypatch.setattr(subject, "read_build_path_wire_result", tracked_read)
    try:
        result = subject.run_build_path_wire(_collaborators(FreeCAD, lambda _d: events.append("validate")), document.Name, "Created", [{"sketch": "Seed", "geo_index": 0}], 0.5, None, "error")
        assert result["success"] is True
        created = document.getObject("Created")
        assert created is not None
        assert "Part::Feature" in created.TypeId
        assert created.Shape is not None and not created.Shape.isNull()
        assert events == ["apply", "recompute", "inspect", "validate"]
    finally:
        FreeCAD.closeDocument(document.Name)


def test_build_path_wire_native_validation_failure_restores_complete_state():
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.build_path_wire import run_build_path_wire

    document = FreeCAD.newDocument("MCPBuildPathWireNativeRollback")
    _prepare(document)
    state_before = _model_state(document)
    try:
        result = run_build_path_wire(
            _collaborators(FreeCAD, lambda _d: (_ for _ in ()).throw(RuntimeError("forced validation failure"))),
            document.Name, "Created", [{"sketch": "Seed", "geo_index": 0}], 0.5, None, "error",
        )
        assert result["success"] is False
        assert result["error_code"] == "DOCUMENT_HEALTH_DEGRADED"
        assert result["rollback_succeeded"] is True
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_build_path_wire_native_apply_failure_restores(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import build_path_wire as subject

    document = FreeCAD.newDocument("MCPBuildPathWireNativeApplyFailure")
    _prepare(document)
    state_before = _model_state(document)
    original = subject.apply_build_path_wire

    def mutates_then_raises(admitted, request):
        original(admitted, request)
        admitted.addObject("App::FeaturePython", "TransientSupport")
        raise RuntimeError("forced failure after structural effects")

    monkeypatch.setattr(subject, "apply_build_path_wire", mutates_then_raises)
    try:
        result = subject.run_build_path_wire(_collaborators(FreeCAD, lambda _d: None), document.Name, "Created", [{"sketch": "Seed", "geo_index": 0}], 0.5, None, "error")
        assert result["success"] is False
        assert result["native_status"] == "ApplyFailed"
        assert document.getObject("TransientSupport") is None
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_build_path_wire_native_recompute_failure_rolls_back(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import build_path_wire as subject

    document = FreeCAD.newDocument("MCPBuildPathWireNativeRecomputeFailure")

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
    original = subject.apply_build_path_wire

    def arm(admitted, request):
        receipt = original(admitted, request)
        proxy.armed = True
        probe.touch()
        return receipt

    monkeypatch.setattr(subject, "apply_build_path_wire", arm)
    try:
        result = subject.run_build_path_wire(_collaborators(FreeCAD, lambda _d: None), document.Name, "Created", [{"sketch": "Seed", "geo_index": 0}], 0.5, None, "error")
        assert result["success"] is False
        assert result["native_status"] == "RecomputeFailed"
        assert _model_state(document) == state_before
    finally:
        proxy.armed = False
        FreeCAD.closeDocument(document.Name)


def test_build_path_wire_native_rollback_failure_is_uncertain_and_fences(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import build_path_wire as subject

    document = FreeCAD.newDocument("MCPBuildPathWireNativeRollbackFailure")

    class PersistentFailureProbe:
        armed = False

        def execute(self, _object):
            if self.armed:
                raise RuntimeError("persistent recompute failure blocks restoration")

    proxy = PersistentFailureProbe()
    probe = document.addObject("App::FeaturePython", "PersistentFailureProbe")
    probe.Proxy = proxy
    _prepare(document)
    original = subject.apply_build_path_wire

    def arm(admitted, request):
        receipt = original(admitted, request)
        proxy.armed = True
        probe.touch()
        return receipt

    monkeypatch.setattr(subject, "apply_build_path_wire", arm)
    collaborators = _collaborators(FreeCAD, lambda _d: None)
    try:
        result = subject.run_build_path_wire(collaborators, document.Name, "Created", [{"sketch": "Seed", "geo_index": 0}], 0.5, None, "error")
        proxy.armed = False
        fenced = subject.run_build_path_wire(collaborators, document.Name, "Created", [{"sketch": "Seed", "geo_index": 0}], 0.5, None, "error")
        assert result["outcome"] == "uncertain" or result["success"] is False
        assert fenced["success"] is False
    finally:
        proxy.armed = False
        FreeCAD.closeDocument(document.Name)


def test_build_path_wire_native_inspection_failure_rolls_back(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import build_path_wire as subject

    document = FreeCAD.newDocument("MCPBuildPathWireNativeInspectionFailure")
    _prepare(document)
    state_before = _model_state(document)

    def reject(_document, _receipt):
        raise subject.BuildPathWireError("CREATED_OBJECT_WRONG_TYPE", "forced inspection failure")

    monkeypatch.setattr(subject, "read_build_path_wire_result", reject)
    try:
        result = subject.run_build_path_wire(_collaborators(FreeCAD, lambda _d: None), document.Name, "Created", [{"sketch": "Seed", "geo_index": 0}], 0.5, None, "error")
        assert result["success"] is False
        assert result["error_code"] == "CREATED_OBJECT_WRONG_TYPE"
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_build_path_wire_native_postcondition_cannot_write():
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.build_path_wire import run_build_path_wire

    document = FreeCAD.newDocument("MCPBuildPathWireReadOnlyPostcondition")
    anchor = document.addObject("App::FeaturePython", "Anchor")
    _prepare(document)
    state_before = _model_state(document)

    def validate(_admitted):
        anchor.Label = "Unvalidated change"

    try:
        result = run_build_path_wire(_collaborators(FreeCAD, validate), document.Name, "Created", [{"sketch": "Seed", "geo_index": 0}], 0.5, None, "error")
        assert result["outcome"] == "rejected"
        assert result["native_status"] == "PostconditionFailed"
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)
