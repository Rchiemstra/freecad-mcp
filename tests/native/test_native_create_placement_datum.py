"""Native qualification matrix for ``create_placement_datum``."""

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
    from tests.typed_feature_native_setup import prepare_native_document

    prepare_native_document(document, "edge_feature")
    return document.getObject("Body")


def test_create_placement_datum_native_success_inspects_after_recompute(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import create_placement_datum as subject

    document = FreeCAD.newDocument("MCPCreatePlacementDatumNativeSuccess")
    events = []

    class RecomputeProbe:
        def execute(self, _object):
            events.append("recompute")

    probe = document.addObject("App::FeaturePython", "RecomputeProbe")
    probe.Proxy = RecomputeProbe()
    _prepare(document)
    events.clear()
    original_apply = subject.apply_create_placement_datum
    original_read = subject.read_create_placement_datum_result

    def tracked_apply(admitted, request):
        events.append("apply")
        probe.touch()
        return original_apply(admitted, request)

    def tracked_read(admitted, receipt):
        events.append("inspect")
        return original_read(admitted, receipt)

    monkeypatch.setattr(subject, "apply_create_placement_datum", tracked_apply)
    monkeypatch.setattr(subject, "read_create_placement_datum_result", tracked_read)
    try:
        result = subject.run_create_placement_datum(_collaborators(FreeCAD, lambda _d: events.append("validate")), document.Name, "Body", "Created", "Pad:Face1", True, None)
        assert result["success"] is True
        assert events == ["apply", "recompute", "inspect", "validate"]
    finally:
        FreeCAD.closeDocument(document.Name)


def test_create_placement_datum_native_validation_failure_restores_complete_state():
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.create_placement_datum import run_create_placement_datum

    document = FreeCAD.newDocument("MCPCreatePlacementDatumNativeRollback")
    _prepare(document)
    state_before = _model_state(document)
    try:
        result = run_create_placement_datum(
            _collaborators(FreeCAD, lambda _d: (_ for _ in ()).throw(RuntimeError("forced validation failure"))),
            document.Name, "Body", "Created", "Pad:Face1", True, None,
        )
        assert result["success"] is False
        assert result["error_code"] == "DOCUMENT_HEALTH_DEGRADED"
        assert result["rollback_succeeded"] is True
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_create_placement_datum_native_apply_failure_restores(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import create_placement_datum as subject

    document = FreeCAD.newDocument("MCPCreatePlacementDatumNativeApplyFailure")
    _prepare(document)
    state_before = _model_state(document)
    original = subject.apply_create_placement_datum

    def mutates_then_raises(admitted, request):
        original(admitted, request)
        admitted.addObject("App::FeaturePython", "TransientSupport")
        raise RuntimeError("forced failure after structural effects")

    monkeypatch.setattr(subject, "apply_create_placement_datum", mutates_then_raises)
    try:
        result = subject.run_create_placement_datum(_collaborators(FreeCAD, lambda _d: None), document.Name, "Body", "Created", "Pad:Face1", True, None)
        assert result["success"] is False
        assert result["native_status"] == "ApplyFailed"
        assert document.getObject("TransientSupport") is None
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_create_placement_datum_native_recompute_failure_rolls_back(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import create_placement_datum as subject

    document = FreeCAD.newDocument("MCPCreatePlacementDatumNativeRecomputeFailure")

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
    original = subject.apply_create_placement_datum

    def arm(admitted, request):
        receipt = original(admitted, request)
        proxy.armed = True
        probe.touch()
        return receipt

    monkeypatch.setattr(subject, "apply_create_placement_datum", arm)
    try:
        result = subject.run_create_placement_datum(_collaborators(FreeCAD, lambda _d: None), document.Name, "Body", "Created", "Pad:Face1", True, None)
        assert result["success"] is False
        assert result["native_status"] == "RecomputeFailed"
        assert _model_state(document) == state_before
    finally:
        proxy.armed = False
        FreeCAD.closeDocument(document.Name)


def test_create_placement_datum_native_rollback_failure_is_uncertain_and_fences(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import create_placement_datum as subject

    document = FreeCAD.newDocument("MCPCreatePlacementDatumNativeRollbackFailure")

    class PersistentFailureProbe:
        armed = False

        def execute(self, _object):
            if self.armed:
                raise RuntimeError("persistent recompute failure blocks restoration")

    proxy = PersistentFailureProbe()
    probe = document.addObject("App::FeaturePython", "PersistentFailureProbe")
    probe.Proxy = proxy
    _prepare(document)
    original = subject.apply_create_placement_datum

    def arm(admitted, request):
        receipt = original(admitted, request)
        proxy.armed = True
        probe.touch()
        return receipt

    monkeypatch.setattr(subject, "apply_create_placement_datum", arm)
    collaborators = _collaborators(FreeCAD, lambda _d: None)
    try:
        result = subject.run_create_placement_datum(collaborators, document.Name, "Body", "Created", "Pad:Face1", True, None)
        proxy.armed = False
        fenced = subject.run_create_placement_datum(collaborators, document.Name, "Body", "Created", "Pad:Face1", True, None)
        assert result["outcome"] == "uncertain" or result["success"] is False
        assert fenced["success"] is False
    finally:
        proxy.armed = False
        FreeCAD.closeDocument(document.Name)


def test_create_placement_datum_native_inspection_failure_rolls_back(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import create_placement_datum as subject

    document = FreeCAD.newDocument("MCPCreatePlacementDatumNativeInspectionFailure")
    _prepare(document)
    state_before = _model_state(document)

    def reject(_document, _receipt):
        raise subject.CreatePlacementDatumError("CREATED_OBJECT_WRONG_TYPE", "forced inspection failure")

    monkeypatch.setattr(subject, "read_create_placement_datum_result", reject)
    try:
        result = subject.run_create_placement_datum(_collaborators(FreeCAD, lambda _d: None), document.Name, "Body", "Created", "Pad:Face1", True, None)
        assert result["success"] is False
        assert result["error_code"] == "CREATED_OBJECT_WRONG_TYPE"
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_create_placement_datum_native_postcondition_cannot_write():
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.create_placement_datum import run_create_placement_datum

    document = FreeCAD.newDocument("MCPCreatePlacementDatumReadOnlyPostcondition")
    anchor = document.addObject("App::FeaturePython", "Anchor")
    _prepare(document)
    state_before = _model_state(document)

    def validate(_admitted):
        anchor.Label = "Unvalidated change"

    try:
        result = run_create_placement_datum(_collaborators(FreeCAD, validate), document.Name, "Body", "Created", "Pad:Face1", True, None)
        assert result["outcome"] == "rejected"
        assert result["native_status"] == "PostconditionFailed"
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)
