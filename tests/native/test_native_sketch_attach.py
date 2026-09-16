
"""Native collaboration coverage for the typed ``sketch_attach`` mutation."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.core


from tests.native_model_state import model_state as _model_state


def _require_native_collaboration() -> None:
    if os.environ.get("FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION") != "1":
        pytest.skip("Compose FreeCAD is adapter-only; use the branch-built lane")




def _revision_state(document):
    keys = [{"kind": "UnknownModelMutation"}, {"kind": "DocumentStructure"}]
    for name in sorted(
        {item.Name for item in document.Objects}
        | {"RejectedBody", "TransientSupport", "NativeSketch", "NativePad", "NativePocket"}
    ):
        keys.extend(
            {"kind": kind, "subject": name} for kind in ("ObjectExistence", "ObjectStructure")
        )
        item = document.getObject(name)
        if item is not None:
            keys.extend(
                {"kind": "ObjectProperty", "subject": name, "property_name": prop}
                for prop in sorted(item.PropertiesList)
            )
    session = document.beginEditSession("sketch_attach-native-state-probe")
    try:
        snapshot = document.snapshotForEdit(session["session_id"], keys)
        return snapshot["revisions"]
    finally:
        document.cancelEdit(session["session_id"])


def _collaborators(FreeCAD, validator):
    import Part
    import Sketcher

    from addon.FreeCADMCP.collaboration_api import CollaborationAPI
    from addon.FreeCADMCP.rpc_server.placement_codec import dict_to_placement, placement_to_dict
    from addon.FreeCADMCP.rpc_server.rpc_helpers_ops.feature_properties import (
        _set_extrusion_symmetric,
        _set_feature_bool,
    )

    bridge = CollaborationAPI(document_lookup=FreeCAD.getDocument)
    return SimpleNamespace(
        freecad=FreeCAD,
        part=Part,
        sketcher=Sketcher,
        dict_to_placement=dict_to_placement,
        placement_to_dict=placement_to_dict,
        set_extrusion_symmetric=_set_extrusion_symmetric,
        set_feature_bool=_set_feature_bool,
        validate_document_invariants=validator,
        commit_native_mutation=bridge.commit_native_mutation,
    )


def _closed_sketch(document, body, name, radius, *, constrain=True):
    import FreeCAD
    import Part
    import Sketcher

    sketch = body.newObject("Sketcher::SketchObject", name)
    sketch.addGeometry(Part.Circle(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), radius), False)
    if constrain:
        sketch.addConstraint(Sketcher.Constraint("Radius", 0, radius))
        sketch.renameConstraint(0, "R")
    return sketch


def _idle(document, mode: str):
    import FreeCAD
    import Part
    import Sketcher

    if mode == "empty":
        document.recompute()
        return
    body = document.addObject("PartDesign::Body", "Body")
    sketch = _closed_sketch(document, body, "Sketch", 10, constrain=mode != "constraint")
    if mode == "attach":
        document.recompute()
        return
    if mode == "pad":
        document.recompute()
        return
    if mode == "pocket":
        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = (sketch, [""])
        pad.Length = 10
        body.Tip = pad
        _closed_sketch(document, body, "PocketSketch", 4)
        document.recompute()
        return
    if mode == "geometry":
        document.recompute()
        return
    if mode == "constraint":
        document.recompute()
        return
    if mode == "delete_geometry":
        sketch.addGeometry(Part.Point(FreeCAD.Vector(20, 0, 0)), False)
        document.recompute()
        return
    if mode == "delete_constraint":
        sketch.addGeometry(
            Part.LineSegment(FreeCAD.Vector(-1, 15, 0), FreeCAD.Vector(1, 15, 0)),
            False,
        )
        sketch.addConstraint(Sketcher.Constraint("Horizontal", 1))
        sketch.renameConstraint(len(sketch.Constraints) - 1, "Extra")
        document.recompute()
        return
    if mode == "edit":
        document.recompute()
        return
    document.recompute()


def test_sketch_attach_native_success_inspects_after_recompute(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import sketch_attach as body_create_module

    document = FreeCAD.newDocument("MCPSketchAttachNativePhaseOrder")
    events = []

    class RecomputeProbe:
        def execute(self, _object):
            events.append("recompute")

    recompute_probe = document.addObject("App::FeaturePython", "RecomputeProbe")
    recompute_probe.Proxy = RecomputeProbe()
    _idle(document, 'attach')
    events.clear()
    original_apply = body_create_module.apply_sketch_attach
    original_read = body_create_module.read_sketch_attach_result

    def tracked_apply(*args, **kwargs):
        events.append("apply")
        recompute_probe.touch()
        return original_apply(*args, **kwargs)

    def tracked_read(*args, **kwargs):
        events.append("inspect")
        return original_read(*args, **kwargs)

    monkeypatch.setattr(body_create_module, "apply_sketch_attach", tracked_apply)
    monkeypatch.setattr(body_create_module, "read_sketch_attach_result", tracked_read)
    collaborators = _collaborators(FreeCAD, lambda _document: events.append("validate"))
    try:
        result = body_create_module.run_sketch_attach(collaborators, document.Name, "Sketch", "XY_Plane")
        assert result["success"] is True
        assert result["committed"] is True
        assert result["retry_safe"] is False
        assert result['sketch'] == 'Sketch'
        assert events == ["apply", "recompute", "inspect", "validate"]
        created = document.getObject(result['sketch'])
        assert created is not None
        assert created.isDerivedFrom('Sketcher::SketchObject')
        assert created.AttachmentSupport
        assert created.AttachmentSupport[0][0].Name
    finally:
        FreeCAD.closeDocument(document.Name)


def test_sketch_attach_native_validation_failure_restores_complete_state():
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_attach import run_sketch_attach

    document = FreeCAD.newDocument("MCPSketchAttachNativeRollback")
    _idle(document, 'attach')
    state_before = _model_state(document)
    revision_before = _revision_state(document)
    collaborators = _collaborators(
        FreeCAD,
        lambda _document: (_ for _ in ()).throw(RuntimeError("forced validation failure")),
    )
    try:
        result = run_sketch_attach(collaborators, document.Name, "Sketch", "XY_Plane")
        assert result["success"] is False
        assert result["error_code"] == "DOCUMENT_HEALTH_DEGRADED"
        assert result["rollback_succeeded"] is True
        assert _model_state(document) == state_before
        assert _revision_state(document) == revision_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_sketch_attach_native_apply_failure_restores_all_attempted_effects(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import sketch_attach as body_create_module

    document = FreeCAD.newDocument("MCPSketchAttachNativeApplyFailure")
    _idle(document, 'attach')
    state_before = _model_state(document)
    revision_before = _revision_state(document)
    original_apply = body_create_module.apply_sketch_attach

    def mutates_then_raises(*args, **kwargs):
        original_apply(*args, **kwargs)
        args[0].addObject("App::FeaturePython", "TransientSupport")
        raise RuntimeError("forced failure after structural effects")

    monkeypatch.setattr(body_create_module, "apply_sketch_attach", mutates_then_raises)
    collaborators = _collaborators(FreeCAD, lambda _document: None)
    try:
        result = body_create_module.run_sketch_attach(collaborators, document.Name, "Sketch", "XY_Plane")
        assert result["success"] is False
        assert result["native_status"] == "ApplyFailed"
        assert result["committed"] is False
        assert document.getObject("TransientSupport") is None
        assert _model_state(document) == state_before
        assert _revision_state(document) == revision_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_sketch_attach_native_recompute_failure_rolls_back(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import sketch_attach as body_create_module

    document = FreeCAD.newDocument("MCPSketchAttachNativeRecomputeFailure")

    class FailingRecomputeProbe:
        armed = False
        def execute(self, _object):
            if self.armed:
                self.armed = False
                raise RuntimeError("forced native recompute failure")

    proxy = FailingRecomputeProbe()
    probe = document.addObject("App::FeaturePython", "FailingRecomputeProbe")
    probe.Proxy = proxy
    _idle(document, 'attach')
    state_before = _model_state(document)
    revision_before = _revision_state(document)
    original_apply = body_create_module.apply_sketch_attach

    def arm_recompute_failure(*args, **kwargs):
        receipt = original_apply(*args, **kwargs)
        proxy.armed = True
        probe.touch()
        return receipt

    monkeypatch.setattr(body_create_module, "apply_sketch_attach", arm_recompute_failure)
    collaborators = _collaborators(FreeCAD, lambda _document: None)
    try:
        result = body_create_module.run_sketch_attach(collaborators, document.Name, "Sketch", "XY_Plane")
        assert result["success"] is False
        assert result["native_status"] == "RecomputeFailed"
        assert _model_state(document) == state_before
        assert _revision_state(document) == revision_before
    finally:
        proxy.armed = False
        FreeCAD.closeDocument(document.Name)


def test_sketch_attach_native_rollback_failure_is_uncertain_and_fences_document(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import sketch_attach as body_create_module

    document = FreeCAD.newDocument("MCPSketchAttachNativeRollbackFailure")

    class PersistentFailureProbe:
        armed = False
        def execute(self, _object):
            if self.armed:
                raise RuntimeError("persistent recompute failure blocks restoration")

    proxy = PersistentFailureProbe()
    probe = document.addObject("App::FeaturePython", "PersistentFailureProbe")
    probe.Proxy = proxy
    _idle(document, 'attach')
    original_apply = body_create_module.apply_sketch_attach

    def arm_persistent_failure(*args, **kwargs):
        receipt = original_apply(*args, **kwargs)
        proxy.armed = True
        probe.touch()
        return receipt

    monkeypatch.setattr(body_create_module, "apply_sketch_attach", arm_persistent_failure)
    collaborators = _collaborators(FreeCAD, lambda _document: None)
    try:
        result = body_create_module.run_sketch_attach(collaborators, document.Name, "Sketch", "XY_Plane")
        proxy.armed = False
        fenced = body_create_module.run_sketch_attach(collaborators, document.Name, "Sketch", "XY_Plane")
        assert result["success"] is False
        assert result["outcome"] == "uncertain"
        assert result["native_status"] == "RollbackFailed"
        assert result["rollback_succeeded"] is False
        assert result["retry_safe"] is False
        assert fenced["success"] is False
        assert fenced["native_status"] == "RollbackFailed"
    finally:
        proxy.armed = False
        FreeCAD.closeDocument(document.Name)


def test_sketch_attach_native_inspection_failure_rolls_back_after_recompute(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import sketch_attach as body_create_module

    document = FreeCAD.newDocument("MCPSketchAttachNativeInspectionFailure")
    _idle(document, 'attach')
    state_before = _model_state(document)
    revision_before = _revision_state(document)

    def reject_inspection(*_args, **_kwargs):
        raise body_create_module.SketchAttachError(
            "CREATED_OBJECT_WRONG_TYPE", "forced post-recompute inspection failure"
        )

    monkeypatch.setattr(body_create_module, "read_sketch_attach_result", reject_inspection)
    collaborators = _collaborators(FreeCAD, lambda _document: None)
    try:
        result = body_create_module.run_sketch_attach(collaborators, document.Name, "Sketch", "XY_Plane")
        assert result["success"] is False
        assert result["error_code"] == "CREATED_OBJECT_WRONG_TYPE"
        assert result["rollback_succeeded"] is True
        assert _model_state(document) == state_before
        assert _revision_state(document) == revision_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_sketch_attach_native_failure_isolated_and_healthy_rollback_recovers():
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_attach import run_sketch_attach

    failed_document = FreeCAD.newDocument("MCPSketchAttachIsolatedFailure")
    healthy_document = FreeCAD.newDocument("MCPSketchAttachHealthyDocument")
    _idle(failed_document, 'attach')
    _idle(healthy_document, 'attach')
    rejected_names = {failed_document.Name}

    def validator(document):
        if document.Name in rejected_names:
            raise RuntimeError("document-local injected fault")

    collaborators = _collaborators(FreeCAD, validator)
    try:
        failed = run_sketch_attach(collaborators, failed_document.Name, "Sketch", "XY_Plane")
        isolated = run_sketch_attach(collaborators, healthy_document.Name, "Sketch", "XY_Plane")
        rejected_names.clear()
        recovered = run_sketch_attach(collaborators, failed_document.Name, "Sketch", "XY_Plane")
        assert failed["success"] is False
        assert isolated["success"] is True
        assert recovered["success"] is True
    finally:
        FreeCAD.closeDocument(failed_document.Name)
        FreeCAD.closeDocument(healthy_document.Name)


def test_sketch_attach_native_duplicate_and_missing_document_keep_typed_errors():
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_attach import run_sketch_attach

    document = FreeCAD.newDocument("MCPSketchAttachTypedErrors")
    _idle(document, 'attach')
    collaborators = _collaborators(FreeCAD, lambda _: None)
    try:
        first = run_sketch_attach(collaborators, document.Name, "Sketch", "XY_Plane")
        assert first["success"] is True
        before = _model_state(document), _revision_state(document)
        result = run_sketch_attach(collaborators, document.Name, "MissingSketch", "XY_Plane")
        assert result["error_code"] == 'SKETCH_NOT_FOUND'
        assert result["retry_safe"] is True
        assert (_model_state(document), _revision_state(document)) == before
        missing = run_sketch_attach(collaborators, "NoSuchSketchAttachQualificationDocument", "Sketch", "XY_Plane")
        assert missing["error_code"] == "DOCUMENT_NOT_FOUND"
        assert missing["outcome"] == "rejected"
        assert missing["retry_safe"] is True
    finally:
        FreeCAD.closeDocument(document.Name)


@pytest.mark.parametrize("stage", ["apply", "recompute", "inspection", "validation"])
def test_sketch_attach_native_rollback_restores_rich_model(monkeypatch, stage):
    _require_native_collaboration()
    import FreeCAD
    import Part
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import sketch_attach as subject

    document = FreeCAD.newDocument("MCPSketchAttachRichRollback")
    body = document.addObject("PartDesign::Body", "ExistingBody")
    feature = body.newObject("PartDesign::Feature", "Anchor")
    feature.Shape = Part.makeBox(2, 3, 4)
    feature.addProperty("App::PropertyFloat", "ReviewValue")
    feature.ReviewValue = 7
    feature.addProperty("App::PropertyLink", "ReviewLink")
    feature.ReviewLink = body.Origin
    feature.setExpression("ReviewValue", "2 + 5")
    body.Tip = feature

    class RecomputeFailure:
        armed = False
        def execute(self, _object):
            if self.armed:
                self.armed = False
                raise RuntimeError("injected rich-model recompute failure")

    proxy = RecomputeFailure()
    probe = document.addObject("App::FeaturePython", "Probe")
    probe.Proxy = proxy
    _idle(document, 'attach')
    before = _model_state(document), _revision_state(document)
    original_apply = subject.apply_sketch_attach
    original_inspect = subject.read_sketch_attach_result

    def change_model(*args, **kwargs):
        receipt = original_apply(*args, **kwargs)
        admitted = args[0]
        support = admitted.addObject("PartDesign::Feature", "TransientSupport")
        body.addObject(support)
        body.Tip = support
        feature.Label = "Changed"
        feature.Shape = Part.makeCylinder(3, 9)
        feature.Placement.Base = FreeCAD.Vector(5, 6, 7)
        feature.setExpression("ReviewValue", None)
        feature.ReviewValue = 123
        feature.ReviewLink = support
        feature.addProperty("App::PropertyString", "TransientProperty")
        feature.TransientProperty = "must disappear"
        if stage == "apply":
            raise RuntimeError("injected rich-model apply failure")
        if stage == "recompute":
            proxy.armed = True
            probe.touch()
        return receipt

    def inspect(*args, **kwargs):
        if stage == "inspection":
            raise subject.SketchAttachError("INSPECTION_FAILED", "injected inspection failure")
        return original_inspect(*args, **kwargs)

    def validate(_document):
        if stage == "validation":
            raise RuntimeError("injected rich-model validation failure")

    monkeypatch.setattr(subject, "apply_sketch_attach", change_model)
    monkeypatch.setattr(subject, "read_sketch_attach_result", inspect)
    try:
        result = subject.run_sketch_attach(_collaborators(FreeCAD, validate), document.Name, "Sketch", "XY_Plane")
        assert result["outcome"] == "rejected"
        assert result["rollback_succeeded"] is True
        assert result["retry_safe"] is True
        assert (_model_state(document), _revision_state(document)) == before
    finally:
        proxy.armed = False
        FreeCAD.closeDocument(document.Name)


@pytest.mark.parametrize("write", ["property", "structure"])
def test_sketch_attach_native_postcondition_cannot_write(monkeypatch, write):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import sketch_attach as subject

    document = FreeCAD.newDocument("MCPSketchAttachReadOnlyPostcondition")
    anchor = document.addObject("App::FeaturePython", "Anchor")
    _idle(document, 'attach')
    before = _model_state(document), _revision_state(document)

    def validate(admitted):
        if write == "property":
            anchor.Label = "Unvalidated change"
        else:
            admitted.addObject("App::FeaturePython", "UnvalidatedObject")

    try:
        result = subject.run_sketch_attach(_collaborators(FreeCAD, validate), document.Name, "Sketch", "XY_Plane")
        assert result["outcome"] == "rejected"
        assert result["native_status"] == "PostconditionFailed"
        assert (_model_state(document), _revision_state(document)) == before
    finally:
        FreeCAD.closeDocument(document.Name)
