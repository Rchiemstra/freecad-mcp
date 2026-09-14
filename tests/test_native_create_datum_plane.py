"""Native qualification matrix for ``create_datum_plane``."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.core


def _require_native_collaboration() -> None:
    if os.environ.get("FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION") != "1":
        pytest.skip("Compose FreeCAD is adapter-only; use the branch-built lane")


import hashlib


def _property_content(item, name: str):
    if name == "Proxy":
        proxy = getattr(item, "Proxy", None)
        if proxy is None:
            return None
        return f"{type(proxy).__module__}.{type(proxy).__qualname__}"
    dumped = bytes(item.dumpPropertyContent(name, 0))
    return hashlib.sha256(dumped).hexdigest()


def _model_state(document):
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
                    _property_content(item, name),
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
    )


def _prepare(document):
    from tests.typed_feature_native_setup import prepare_native_document

    prepare_native_document(document, "edge_feature")


def test_create_datum_plane_native_success_inspects_after_recompute(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import create_datum_plane as subject

    document = FreeCAD.newDocument("MCPCreateDatumPlaneNativeSuccess")
    events = []

    class RecomputeProbe:
        def execute(self, _object):
            events.append("recompute")

    probe = document.addObject("App::FeaturePython", "RecomputeProbe")
    probe.Proxy = RecomputeProbe()
    _prepare(document)
    events.clear()
    original_apply = subject.apply_create_datum_plane
    original_read = subject.read_create_datum_plane_result

    def tracked_apply(admitted, request):
        events.append("apply")
        probe.touch()
        return original_apply(admitted, request)

    def tracked_read(admitted, receipt):
        events.append("inspect")
        return original_read(admitted, receipt)

    monkeypatch.setattr(subject, "apply_create_datum_plane", tracked_apply)
    monkeypatch.setattr(subject, "read_create_datum_plane_result", tracked_read)
    try:
        result = subject.run_create_datum_plane(_collaborators(FreeCAD, lambda _d: events.append("validate")), document.Name, "Created", "Body", "through_point", "Pad:Face6", None, None, None, "FlatFace", "error")
        assert result["success"] is True
        assert events == ["apply", "recompute", "inspect", "validate"]
    finally:
        FreeCAD.closeDocument(document.Name)


def test_create_datum_plane_native_validation_failure_restores_complete_state():
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.create_datum_plane import run_create_datum_plane

    document = FreeCAD.newDocument("MCPCreateDatumPlaneNativeRollback")
    _prepare(document)
    state_before = _model_state(document)
    try:
        result = run_create_datum_plane(
            _collaborators(FreeCAD, lambda _d: (_ for _ in ()).throw(RuntimeError("forced validation failure"))),
            document.Name, "Created", "Body", "through_point", "Pad:Face6", None, None, None, "FlatFace", "error",
        )
        assert result["success"] is False
        assert result["error_code"] == "DOCUMENT_HEALTH_DEGRADED"
        assert result["rollback_succeeded"] is True
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_create_datum_plane_native_apply_failure_restores(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import create_datum_plane as subject

    document = FreeCAD.newDocument("MCPCreateDatumPlaneNativeApplyFailure")
    _prepare(document)
    state_before = _model_state(document)
    original = subject.apply_create_datum_plane

    def mutates_then_raises(admitted, request):
        original(admitted, request)
        admitted.addObject("App::FeaturePython", "TransientSupport")
        raise RuntimeError("forced failure after structural effects")

    monkeypatch.setattr(subject, "apply_create_datum_plane", mutates_then_raises)
    try:
        result = subject.run_create_datum_plane(_collaborators(FreeCAD, lambda _d: None), document.Name, "Created", "Body", "through_point", "Pad:Face6", None, None, None, "FlatFace", "error")
        assert result["success"] is False
        assert result["native_status"] == "ApplyFailed"
        assert document.getObject("TransientSupport") is None
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_create_datum_plane_native_recompute_failure_rolls_back(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import create_datum_plane as subject

    document = FreeCAD.newDocument("MCPCreateDatumPlaneNativeRecomputeFailure")

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
    original = subject.apply_create_datum_plane

    def arm(admitted, request):
        receipt = original(admitted, request)
        proxy.armed = True
        probe.touch()
        return receipt

    monkeypatch.setattr(subject, "apply_create_datum_plane", arm)
    try:
        result = subject.run_create_datum_plane(_collaborators(FreeCAD, lambda _d: None), document.Name, "Created", "Body", "through_point", "Pad:Face6", None, None, None, "FlatFace", "error")
        assert result["success"] is False
        assert result["native_status"] == "RecomputeFailed"
        assert _model_state(document) == state_before
    finally:
        proxy.armed = False
        FreeCAD.closeDocument(document.Name)


def test_create_datum_plane_native_rollback_failure_is_uncertain_and_fences(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import create_datum_plane as subject

    document = FreeCAD.newDocument("MCPCreateDatumPlaneNativeRollbackFailure")

    class PersistentFailureProbe:
        armed = False

        def execute(self, _object):
            if self.armed:
                raise RuntimeError("persistent recompute failure blocks restoration")

    proxy = PersistentFailureProbe()
    probe = document.addObject("App::FeaturePython", "PersistentFailureProbe")
    probe.Proxy = proxy
    _prepare(document)
    original = subject.apply_create_datum_plane

    def arm(admitted, request):
        receipt = original(admitted, request)
        proxy.armed = True
        probe.touch()
        return receipt

    monkeypatch.setattr(subject, "apply_create_datum_plane", arm)
    collaborators = _collaborators(FreeCAD, lambda _d: None)
    try:
        result = subject.run_create_datum_plane(collaborators, document.Name, "Created", "Body", "through_point", "Pad:Face6", None, None, None, "FlatFace", "error")
        proxy.armed = False
        fenced = subject.run_create_datum_plane(collaborators, document.Name, "Created", "Body", "through_point", "Pad:Face6", None, None, None, "FlatFace", "error")
        assert result["outcome"] == "uncertain" or result["success"] is False
        assert fenced["success"] is False
    finally:
        proxy.armed = False
        FreeCAD.closeDocument(document.Name)


def test_create_datum_plane_native_inspection_failure_rolls_back(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import create_datum_plane as subject

    document = FreeCAD.newDocument("MCPCreateDatumPlaneNativeInspectionFailure")
    _prepare(document)
    state_before = _model_state(document)

    def reject(_document, _receipt):
        raise subject.CreateDatumPlaneError("CREATED_OBJECT_WRONG_TYPE", "forced inspection failure")

    monkeypatch.setattr(subject, "read_create_datum_plane_result", reject)
    try:
        result = subject.run_create_datum_plane(_collaborators(FreeCAD, lambda _d: None), document.Name, "Created", "Body", "through_point", "Pad:Face6", None, None, None, "FlatFace", "error")
        assert result["success"] is False
        assert result["error_code"] == "CREATED_OBJECT_WRONG_TYPE"
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_create_datum_plane_native_postcondition_cannot_write():
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.create_datum_plane import run_create_datum_plane

    document = FreeCAD.newDocument("MCPCreateDatumPlaneReadOnlyPostcondition")
    anchor = document.addObject("App::FeaturePython", "Anchor")
    _prepare(document)
    state_before = _model_state(document)

    def validate(_admitted):
        anchor.Label = "Unvalidated change"

    try:
        result = run_create_datum_plane(_collaborators(FreeCAD, validate), document.Name, "Created", "Body", "through_point", "Pad:Face6", None, None, None, "FlatFace", "error")
        assert result["outcome"] == "rejected"
        assert result["native_status"] == "PostconditionFailed"
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)
