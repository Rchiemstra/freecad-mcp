"""Native qualification matrix for typed ``body_set_tip``.

These tests require the branch-built FreeCAD collaboration API. Run them via
``python ci/qualify_body_set_tip.py --native``. A missing runtime is an error
in that lane, not a pass.
"""

from __future__ import annotations

import hashlib
import os
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.core


def _require_native_collaboration() -> None:
    if os.environ.get("FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION") != "1":
        pytest.skip("Compose FreeCAD is adapter-only; use the branch-built lane")


def _close_all_documents(FreeCAD) -> None:
    for name in list(FreeCAD.listDocuments()):
        try:
            FreeCAD.closeDocument(name)
        except Exception:
            pass


@pytest.fixture(autouse=True)
def _isolate_native_documents():
    if os.environ.get("FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION") != "1":
        yield
        return
    import FreeCAD

    _close_all_documents(FreeCAD)
    yield
    _close_all_documents(FreeCAD)


from tests.native_model_state import model_state as _model_state



def _revision_state(document):
    keys = [{"kind": "UnknownModelMutation"}, {"kind": "DocumentStructure"}]
    for name in sorted(
        {item.Name for item in document.Objects} | {"RejectedBody", "TransientSupport"}
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
    session = document.beginEditSession("body-set-tip-native-state-probe")
    try:
        snapshot = document.snapshotForEdit(session["session_id"], keys)
        return snapshot["revisions"]
    finally:
        document.cancelEdit(session["session_id"])


def _tip_collaborators(FreeCAD, validator):
    from addon.FreeCADMCP.collaboration_api import CollaborationAPI

    bridge = CollaborationAPI(document_lookup=FreeCAD.getDocument)
    return SimpleNamespace(
        validate_document_invariants=validator,
        commit_native_mutation=bridge.commit_native_mutation,
    )


def _must_execute(item) -> int:
    method = getattr(item, "mustExecute", None)
    if callable(method):
        return int(method())
    return int(bool(getattr(item, "MustExecute", False)))


def _assert_document_idle(document) -> None:
    pending = []
    for item in document.Objects:
        state = tuple(item.State)
        must = _must_execute(item)
        if must or "Touched" in state:
            pending.append((item.Name, item.TypeId, state, must))
    assert pending == [], pending


def _origin_xy(body):
    origin = body.Origin
    for feat in getattr(origin, "OriginFeatures", []) or []:
        if feat.Label == "XY_Plane" or feat.Name.endswith("XY") or "XY" in feat.Label:
            return feat
    plane = getattr(origin, "XY_Plane", None)
    if plane is not None:
        return plane
    raise LookupError("XY_Plane not found")


def _add_closed_circle_sketch(body, name: str, radius: float):
    import FreeCAD
    import Part

    sketch = body.newObject("Sketcher::SketchObject", name)
    sketch.AttachmentSupport = [(_origin_xy(body), "")]
    sketch.MapMode = "FlatFace"
    sketch.addGeometry(
        Part.Circle(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), radius),
        False,
    )
    return sketch


def _make_idle_body_with_pad_and_pocket(document):
    """Build a valid idle Body whose Tip can move Pad → Pocket."""

    body = document.addObject("PartDesign::Body", "Body")
    document.recompute()
    pad_sketch = _add_closed_circle_sketch(body, "PadSketch", 10.0)
    pad = body.newObject("PartDesign::Pad", "Pad")
    pad.Profile = pad_sketch
    pad.Length = 10.0
    document.recompute()
    pocket_sketch = _add_closed_circle_sketch(body, "PocketSketch", 4.0)
    pocket = body.newObject("PartDesign::Pocket", "Pocket")
    pocket.Profile = pocket_sketch
    pocket.Length = 5.0
    if hasattr(pocket, "Reversed"):
        pocket.Reversed = True
    document.recompute()
    body.Tip = pad
    document.recompute()
    _assert_document_idle(document)
    assert body.Tip is pad
    return body, pad, pocket


def test_body_set_tip_native_success_inspects_after_recompute(monkeypatch):
    _require_native_collaboration()

    import FreeCAD

    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import (
        body_set_tip as body_set_tip_module,
    )

    document = FreeCAD.newDocument("MCPBodySetTipNativePhaseOrder")
    events = []

    class RecomputeProbe:
        def execute(self, _object):
            events.append("recompute")

    try:
        body, _pad, pocket = _make_idle_body_with_pad_and_pocket(document)
        recompute_probe = document.addObject("App::FeaturePython", "RecomputeProbe")
        recompute_probe.Proxy = RecomputeProbe()
        document.recompute()
        _assert_document_idle(document)
        events.clear()

        original_apply = body_set_tip_module.apply_body_set_tip
        original_read = body_set_tip_module.read_body_set_tip_result

        def tracked_apply(admitted_document, body_name, feature_name):
            events.append("apply")
            recompute_probe.touch()
            return original_apply(admitted_document, body_name, feature_name)

        def tracked_read(admitted_document, receipt):
            events.append("inspect")
            return original_read(admitted_document, receipt)

        monkeypatch.setattr(body_set_tip_module, "apply_body_set_tip", tracked_apply)
        monkeypatch.setattr(body_set_tip_module, "read_body_set_tip_result", tracked_read)
        collaborators = _tip_collaborators(
            FreeCAD, lambda _document: events.append("validate")
        )

        result = body_set_tip_module.run_body_set_tip(
            collaborators, document.Name, body.Name, pocket.Name
        )

        assert result["success"] is True
        assert result["committed"] is True
        assert result["retry_safe"] is False
        assert result["body"] == body.Name
        assert result["tip"] == pocket.Name
        assert result["feature"] == pocket.Name
        assert events == ["apply", "recompute", "inspect", "validate"]
        assert body.Tip is pocket
        _assert_document_idle(document)
    finally:
        FreeCAD.closeDocument(document.Name)


def test_body_set_tip_native_validation_failure_restores_complete_state():
    _require_native_collaboration()

    import FreeCAD

    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.body_set_tip import (
        run_body_set_tip,
    )

    document = FreeCAD.newDocument("MCPBodySetTipNativeRollback")
    try:
        anchor = document.addObject("App::FeaturePython", "ExistingAnchor")
        anchor.Label = "Before"
        body, pad, pocket = _make_idle_body_with_pad_and_pocket(document)
        state_before = _model_state(document)
        revision_before = _revision_state(document)
        collaborators = _tip_collaborators(
            FreeCAD,
            lambda _document: (_ for _ in ()).throw(
                RuntimeError("forced body tip validation failure")
            ),
        )

        result = run_body_set_tip(collaborators, document.Name, body.Name, pocket.Name)

        assert result["success"] is False
        assert result["error_code"] == "DOCUMENT_HEALTH_DEGRADED"
        assert result["rollback_succeeded"] is True
        assert body.Tip is pad
        assert _model_state(document) == state_before
        assert _revision_state(document) == revision_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_body_set_tip_native_apply_failure_restores_all_attempted_effects(monkeypatch):
    _require_native_collaboration()

    import FreeCAD

    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import (
        body_set_tip as body_set_tip_module,
    )

    document = FreeCAD.newDocument("MCPBodySetTipNativeApplyFailure")
    try:
        anchor = document.addObject("App::FeaturePython", "ExistingAnchor")
        anchor.Label = "Before"
        body, pad, pocket = _make_idle_body_with_pad_and_pocket(document)
        state_before = _model_state(document)
        revision_before = _revision_state(document)
        original_apply = body_set_tip_module.apply_body_set_tip

        def mutates_then_raises(admitted_document, body_name, feature_name):
            original_apply(admitted_document, body_name, feature_name)
            admitted_document.addObject("App::FeaturePython", "TransientSupport")
            anchor.Label = "Changed by rejected apply"
            raise RuntimeError("forced failure after structural effects")

        monkeypatch.setattr(body_set_tip_module, "apply_body_set_tip", mutates_then_raises)
        collaborators = _tip_collaborators(FreeCAD, lambda _document: None)

        result = body_set_tip_module.run_body_set_tip(
            collaborators, document.Name, body.Name, pocket.Name
        )

        assert result["success"] is False
        assert result["native_status"] == "ApplyFailed"
        assert result["committed"] is False
        assert body.Tip is pad
        assert document.getObject("TransientSupport") is None
        assert _model_state(document) == state_before
        assert _revision_state(document) == revision_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_body_set_tip_native_recompute_failure_rolls_back(monkeypatch):
    _require_native_collaboration()

    import FreeCAD

    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import (
        body_set_tip as body_set_tip_module,
    )

    document = FreeCAD.newDocument("MCPBodySetTipNativeRecomputeFailure")

    class FailingRecomputeProbe:
        armed = False

        def execute(self, _object):
            if self.armed:
                self.armed = False
                raise RuntimeError("forced native recompute failure")

    proxy = FailingRecomputeProbe()
    try:
        body, pad, pocket = _make_idle_body_with_pad_and_pocket(document)
        probe = document.addObject("App::FeaturePython", "FailingRecomputeProbe")
        probe.Proxy = proxy
        document.recompute()
        _assert_document_idle(document)
        state_before = _model_state(document)
        revision_before = _revision_state(document)
        original_apply = body_set_tip_module.apply_body_set_tip

        def arm_recompute_failure(admitted_document, body_name, feature_name):
            receipt = original_apply(admitted_document, body_name, feature_name)
            proxy.armed = True
            probe.touch()
            return receipt

        monkeypatch.setattr(body_set_tip_module, "apply_body_set_tip", arm_recompute_failure)
        collaborators = _tip_collaborators(FreeCAD, lambda _document: None)

        result = body_set_tip_module.run_body_set_tip(
            collaborators, document.Name, body.Name, pocket.Name
        )

        assert result["success"] is False
        assert result["native_status"] == "RecomputeFailed"
        assert body.Tip is pad
        assert _model_state(document) == state_before
        assert _revision_state(document) == revision_before
    finally:
        proxy.armed = False
        FreeCAD.closeDocument(document.Name)


def test_body_set_tip_native_rollback_failure_is_uncertain_and_fences_document(
    monkeypatch,
):
    _require_native_collaboration()

    import FreeCAD

    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import (
        body_set_tip as body_set_tip_module,
    )

    document = FreeCAD.newDocument("MCPBodySetTipNativeRollbackFailure")

    class PersistentFailureProbe:
        armed = False

        def execute(self, _object):
            if self.armed:
                raise RuntimeError("persistent recompute failure blocks restoration")

    proxy = PersistentFailureProbe()
    try:
        body, _pad, pocket = _make_idle_body_with_pad_and_pocket(document)
        probe = document.addObject("App::FeaturePython", "PersistentFailureProbe")
        probe.Proxy = proxy
        document.recompute()
        _assert_document_idle(document)
        original_apply = body_set_tip_module.apply_body_set_tip

        def arm_persistent_failure(admitted_document, body_name, feature_name):
            receipt = original_apply(admitted_document, body_name, feature_name)
            proxy.armed = True
            probe.touch()
            return receipt

        monkeypatch.setattr(body_set_tip_module, "apply_body_set_tip", arm_persistent_failure)
        collaborators = _tip_collaborators(FreeCAD, lambda _document: None)

        result = body_set_tip_module.run_body_set_tip(
            collaborators, document.Name, body.Name, pocket.Name
        )
        fenced = body_set_tip_module.run_body_set_tip(
            collaborators, document.Name, body.Name, pocket.Name
        )

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


def test_body_set_tip_native_inspection_failure_rolls_back_after_recompute(monkeypatch):
    _require_native_collaboration()

    import FreeCAD

    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import (
        body_set_tip as body_set_tip_module,
    )

    document = FreeCAD.newDocument("MCPBodySetTipNativeInspectionFailure")
    try:
        body, pad, pocket = _make_idle_body_with_pad_and_pocket(document)
        state_before = _model_state(document)
        revision_before = _revision_state(document)

        def reject_inspection(_document, _receipt):
            raise body_set_tip_module.BodySetTipError(
                "TIP_NOT_UPDATED", "forced post-recompute inspection failure"
            )

        monkeypatch.setattr(body_set_tip_module, "read_body_set_tip_result", reject_inspection)
        collaborators = _tip_collaborators(FreeCAD, lambda _document: None)

        result = body_set_tip_module.run_body_set_tip(
            collaborators, document.Name, body.Name, pocket.Name
        )

        assert result["success"] is False
        assert result["error_code"] == "TIP_NOT_UPDATED"
        assert result["rollback_succeeded"] is True
        assert body.Tip is pad
        assert _model_state(document) == state_before
        assert _revision_state(document) == revision_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_body_set_tip_native_failure_isolated_and_healthy_rollback_recovers():
    _require_native_collaboration()

    import FreeCAD

    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.body_set_tip import (
        run_body_set_tip,
    )

    failed_document = FreeCAD.newDocument("MCPBodySetTipIsolatedFailure")
    healthy_document = FreeCAD.newDocument("MCPBodySetTipHealthyDocument")
    rejected_names = {failed_document.Name}

    def validator(document):
        if document.Name in rejected_names:
            raise RuntimeError("document-local injected fault")

    collaborators = _tip_collaborators(FreeCAD, validator)
    try:
        failed_body, failed_pad, failed_pocket = _make_idle_body_with_pad_and_pocket(
            failed_document
        )
        healthy_body, _healthy_pad, healthy_pocket = _make_idle_body_with_pad_and_pocket(
            healthy_document
        )
        failed = run_body_set_tip(
            collaborators, failed_document.Name, failed_body.Name, failed_pocket.Name
        )
        assert failed["success"] is False
        assert failed["rollback_succeeded"] is True
        assert failed_body.Tip is failed_pad

        isolated = run_body_set_tip(
            collaborators, healthy_document.Name, healthy_body.Name, healthy_pocket.Name
        )
        assert isolated["success"] is True
        assert healthy_body.Tip is healthy_pocket

        rejected_names.clear()
        recovered = run_body_set_tip(
            collaborators, failed_document.Name, failed_body.Name, failed_pocket.Name
        )
        assert recovered["success"] is True
        assert failed_body.Tip is failed_pocket
    finally:
        FreeCAD.closeDocument(failed_document.Name)
        FreeCAD.closeDocument(healthy_document.Name)


def test_body_set_tip_native_missing_targets_keep_typed_errors():
    _require_native_collaboration()
    import FreeCAD

    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.body_set_tip import (
        run_body_set_tip,
    )

    document = FreeCAD.newDocument("MCPBodySetTipTypedErrors")
    collaborators = _tip_collaborators(FreeCAD, lambda _: None)
    try:
        body, pad, _pocket = _make_idle_body_with_pad_and_pocket(document)
        before = _model_state(document), _revision_state(document)
        missing_feature = run_body_set_tip(
            collaborators, document.Name, body.Name, "NoSuchFeature"
        )
        assert missing_feature["error_code"] == "FEATURE_NOT_FOUND"
        assert missing_feature["native_status"] == "ApplyFailed"
        assert missing_feature["rollback_succeeded"] is True
        assert body.Tip is pad
        assert (_model_state(document), _revision_state(document)) == before
        missing_body = run_body_set_tip(
            collaborators, document.Name, "NoSuchBody", pad.Name
        )
        assert missing_body["error_code"] == "BODY_NOT_FOUND"
        missing = run_body_set_tip(
            collaborators, "NoSuchTipQualificationDocument", "Body", "Pad"
        )
        assert missing["error_code"] == "DOCUMENT_NOT_FOUND"
        assert missing["outcome"] == "rejected"
        assert missing["retry_safe"] is True
    finally:
        FreeCAD.closeDocument(document.Name)


def test_body_set_tip_native_rejects_feature_from_other_body():
    _require_native_collaboration()
    import FreeCAD

    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.body_set_tip import (
        run_body_set_tip,
    )

    document = FreeCAD.newDocument("MCPBodySetTipForeignFeature")
    collaborators = _tip_collaborators(FreeCAD, lambda _: None)
    try:
        body_one = document.addObject("PartDesign::Body", "BodyOne")
        body_two = document.addObject("PartDesign::Body", "BodyTwo")
        document.recompute()
        pad_one_sketch = _add_closed_circle_sketch(body_one, "PadOneSketch", 10.0)
        pad_one = body_one.newObject("PartDesign::Pad", "PadOne")
        pad_one.Profile = pad_one_sketch
        pad_one.Length = 10.0
        pad_two_sketch = _add_closed_circle_sketch(body_two, "PadTwoSketch", 10.0)
        pad_two = body_two.newObject("PartDesign::Pad", "PadTwo")
        pad_two.Profile = pad_two_sketch
        pad_two.Length = 10.0
        document.recompute()
        body_one.Tip = pad_one
        document.recompute()
        result = run_body_set_tip(collaborators, document.Name, "BodyOne", "PadTwo")
        assert result["success"] is False
        assert result["error_code"] == "FEATURE_NOT_IN_BODY"
        assert body_one.Tip is pad_one
    finally:
        FreeCAD.closeDocument(document.Name)


@pytest.mark.parametrize("stage", ["apply", "recompute", "inspection", "validation"])
def test_body_set_tip_native_rollback_restores_rich_model(monkeypatch, stage):
    _require_native_collaboration()
    import FreeCAD
    import Part

    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import body_set_tip as subject

    document = FreeCAD.newDocument("MCPBodySetTipRichRollback")
    try:
        body, pad, pocket = _make_idle_body_with_pad_and_pocket(document)
        feature = pad
        feature.addProperty("App::PropertyFloat", "ReviewValue")
        feature.ReviewValue = 7
        feature.addProperty("App::PropertyLink", "ReviewLink")
        feature.ReviewLink = body.Origin
        feature.setExpression("ReviewValue", "2 + 5")

        class RecomputeFailure:
            armed = False

            def execute(self, _object):
                if self.armed:
                    self.armed = False
                    raise RuntimeError("injected rich-model recompute failure")

        proxy = RecomputeFailure()
        probe = document.addObject("App::FeaturePython", "Probe")
        probe.Proxy = proxy
        document.recompute()
        _assert_document_idle(document)
        before = _model_state(document), _revision_state(document)
        original_apply = subject.apply_body_set_tip
        original_inspect = subject.read_body_set_tip_result

        def change_model(admitted, body_name, feature_name):
            receipt = original_apply(admitted, body_name, feature_name)
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

        def inspect(admitted, receipt):
            if stage == "inspection":
                raise subject.BodySetTipError("INSPECTION_FAILED", "injected inspection failure")
            return original_inspect(admitted, receipt)

        def validate(_document):
            if stage == "validation":
                raise RuntimeError("injected rich-model validation failure")

        monkeypatch.setattr(subject, "apply_body_set_tip", change_model)
        monkeypatch.setattr(subject, "read_body_set_tip_result", inspect)
        result = subject.run_body_set_tip(
            _tip_collaborators(FreeCAD, validate), document.Name, body.Name, pocket.Name
        )
        assert result["outcome"] == "rejected"
        assert result["rollback_succeeded"] is True
        assert result["retry_safe"] is True
        assert (_model_state(document), _revision_state(document)) == before
        assert body.Tip is pad
    finally:
        FreeCAD.closeDocument(document.Name)


@pytest.mark.parametrize("write", ["property", "structure"])
def test_body_set_tip_native_postcondition_cannot_write(monkeypatch, write):
    _require_native_collaboration()
    import FreeCAD

    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import body_set_tip as subject

    document = FreeCAD.newDocument("MCPBodySetTipReadOnlyPostcondition")
    try:
        anchor = document.addObject("App::FeaturePython", "Anchor")
        body, pad, pocket = _make_idle_body_with_pad_and_pocket(document)
        document.recompute()
        before = _model_state(document), _revision_state(document)

        def validate(admitted):
            if write == "property":
                anchor.Label = "Unvalidated change"
            else:
                admitted.addObject("App::FeaturePython", "UnvalidatedObject")

        result = subject.run_body_set_tip(
            _tip_collaborators(FreeCAD, validate), document.Name, body.Name, pocket.Name
        )
        assert result["outcome"] == "rejected"
        assert result["native_status"] == "PostconditionFailed"
        assert body.Tip is pad
        assert (_model_state(document), _revision_state(document)) == before
    finally:
        FreeCAD.closeDocument(document.Name)
