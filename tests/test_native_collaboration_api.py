"""Cross-track availability check for the branch-built native collaboration API."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.core


def _require_native_collaboration() -> None:
    if os.environ.get("FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION") != "1":
        pytest.skip("Compose FreeCAD is adapter-only; use the branch-built lane")


def _model_state(document):
    return tuple(
        (item.Name, item.TypeId, str(item.Label))
        for item in document.Objects
    )


def _wildcard_revision(document):
    keys = [{"kind": "UnknownModelMutation"}]
    session = document.beginEditSession("body-create-native-state-probe")
    try:
        snapshot = document.snapshotForEdit(session["session_id"], keys)
        return snapshot["revisions"][0]["revision"]
    finally:
        document.cancelEdit(session["session_id"])


def _body_collaborators(FreeCAD, validator):
    from addon.FreeCADMCP.collaboration_api import CollaborationAPI

    bridge = CollaborationAPI(document_lookup=FreeCAD.getDocument)
    return SimpleNamespace(
        validate_document_invariants=validator,
        commit_body_create_mutation=bridge.commit_body_create_mutation,
    )


def test_branch_built_freecad_exposes_the_frozen_collaboration_api():
    _require_native_collaboration()

    import FreeCAD

    document = FreeCAD.newDocument("MCPNativeCollaborationAvailability")
    try:
        for method in (
            "canWriteRecoverySnapshot",
            "beginEditSession",
            "snapshotForEdit",
            "prepareEdit",
            "prepareEditAsync",
            "preparedEditStatus",
            "cancelPreparedEdit",
            "takePreparedEdit",
            "commitEdit",
            "cancelEdit",
            "editSessionStatus",
            "commitCompatibilityMutation",
        ):
            assert callable(getattr(document, method, None)), method
        for method in (
            "writeRecoverySnapshotToTransientDir",
            "advanceDocumentCollaborationEpoch",
        ):
            assert callable(getattr(FreeCAD, method, None)), method
    finally:
        FreeCAD.closeDocument(document.Name)


def test_typed_cad_adapter_publishes_one_exact_structural_revision_event():
    _require_native_collaboration()

    import FreeCAD

    from addon.FreeCADMCP.collaboration_api import CollaborationAPI
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_mutation import (
        run_cad_mutation,
    )
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.object_crud import (
        create_object,
    )
    from addon.FreeCADMCP.rpc_server.mutation_guard_ops.validate_invariants import (
        validate_document_invariants,
    )

    document = FreeCAD.newDocument("MCPTypedCadNativeAttribution")
    native_results = []
    bridge = CollaborationAPI(document_lookup=FreeCAD.getDocument)
    revision_keys = [
        {"kind": "ObjectExistence", "subject": "RemoteFeature"},
        {"kind": "ObjectStructure", "subject": "RemoteFeature"},
        {"kind": "DocumentStructure"},
        {"kind": "UnknownModelMutation"},
    ]
    session = document.beginEditSession("phase-15-revision-baseline")
    snapshot = document.snapshotForEdit(session["session_id"], revision_keys)
    document.cancelEdit(session["session_id"])
    revisions_before = {
        (revision["kind"], revision["subject"]): revision["revision"]
        for revision in snapshot["revisions"]
    }

    class RecordingAPI:
        def commit_compatibility_mutation(
            self, document_name, callback, *, structural=False
        ):
            native_result = bridge.commit_compatibility_mutation(
                document_name, callback, structural=structural
            )
            native_results.append(native_result)
            return native_result

    collaborators = SimpleNamespace(
        freecad=FreeCAD,
        create_object_gui=lambda document_name, obj: (
            FreeCAD.getDocument(document_name).addObject(obj.type, obj.name)
            is not None
        ),
        validate_document_invariants=validate_document_invariants,
        commit_compatibility_mutation=(
            RecordingAPI().commit_compatibility_mutation
        ),
    )
    facade = SimpleNamespace(
        _cad_collaborators=collaborators,
        _dispatch_gui=lambda callback: callback(),
        _adapt_gui_mutation_result=lambda result, success_fields=None: {
            "success": result is True,
            **(success_fields or {}),
        },
    )

    try:
        result = create_object(
            facade,
            document.Name,
            {"Type": "App::FeaturePython", "Name": "RemoteFeature"},
        )
        assert result == {"success": True, "object_name": "RemoteFeature"}
        assert len(native_results) == 1
        assert native_results[0]["status"] == "Committed"
        assert native_results[0]["committed"] is True
        published = native_results[0]["published_revisions"]
        assert {change["kind"] for change in published} == {
            "ObjectExistence",
            "ObjectStructure",
            "DocumentStructure",
            "UnknownModelMutation",
        }
        assert len(published) == len(revision_keys)
        assert all(
            change["revision"]
            == revisions_before[(change["kind"], change["subject"])] + 1
            for change in published
        )

        failed = run_cad_mutation(
            collaborators,
            document.Name,
            lambda: (
                document.addObject("App::FeaturePython", "RolledBackFeature")
                and False
            ),
            structural=True,
        )
        assert failed is False
        assert document.getObject("RolledBackFeature") is None
        assert len(native_results) == 1
    finally:
        FreeCAD.closeDocument(document.Name)


def test_body_create_native_success_inspects_after_recompute(monkeypatch):
    """Observe the body-specific phase order through the real native boundary."""

    _require_native_collaboration()

    import FreeCAD

    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import (
        body_create as body_create_module,
    )

    document = FreeCAD.newDocument("MCPBodyCreateNativePhaseOrder")
    events = []

    class RecomputeProbe:
        def execute(self, _object):
            events.append("recompute")

    recompute_probe = document.addObject("App::FeaturePython", "RecomputeProbe")
    recompute_probe.Proxy = RecomputeProbe()
    document.recompute()
    events.clear()

    original_apply = body_create_module.apply_body_create
    original_read = body_create_module.read_body_result

    def tracked_apply(admitted_document, body_name):
        events.append("apply")
        recompute_probe.touch()
        return original_apply(admitted_document, body_name)

    def tracked_read(admitted_document, receipt):
        events.append("inspect")
        return original_read(admitted_document, receipt)

    monkeypatch.setattr(body_create_module, "apply_body_create", tracked_apply)
    monkeypatch.setattr(body_create_module, "read_body_result", tracked_read)
    collaborators = _body_collaborators(
        FreeCAD, lambda _document: events.append("validate")
    )

    try:
        result = body_create_module.run_body_create(
            collaborators, document.Name, "NativeBody"
        )

        assert result["success"] is True
        assert result["committed"] is True
        assert result["retry_safe"] is False
        assert result["body"] == "NativeBody"
        assert events == ["apply", "recompute", "inspect", "validate"]
        body = document.getObject(result["body"])
        assert body is not None
        assert body.isDerivedFrom("PartDesign::Body")
    finally:
        FreeCAD.closeDocument(document.Name)


def test_body_create_native_validation_failure_restores_complete_state():
    """Exercise the body-specific wrapper against the real native boundary."""

    _require_native_collaboration()

    import FreeCAD

    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.body_create import (
        run_body_create,
    )

    document = FreeCAD.newDocument("MCPBodyCreateNativeRollback")
    anchor = document.addObject("App::FeaturePython", "ExistingAnchor")
    anchor.Label = "Before"
    document.recompute()
    state_before = _model_state(document)
    revision_before = _wildcard_revision(document)
    collaborators = _body_collaborators(
        FreeCAD,
        lambda _document: (_ for _ in ()).throw(
            RuntimeError("forced body validation failure")
        ),
    )

    try:
        result = run_body_create(collaborators, document.Name, "RejectedBody")

        assert result["success"] is False
        assert result["error_code"] == "DOCUMENT_HEALTH_DEGRADED"
        assert result["rollback_succeeded"] is True
        assert document.getObject("RejectedBody") is None
        assert _model_state(document) == state_before
        assert _wildcard_revision(document) == revision_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_body_create_native_apply_failure_restores_all_attempted_effects(monkeypatch):
    _require_native_collaboration()

    import FreeCAD

    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import (
        body_create as body_create_module,
    )

    document = FreeCAD.newDocument("MCPBodyCreateNativeApplyFailure")
    anchor = document.addObject("App::FeaturePython", "ExistingAnchor")
    anchor.Label = "Before"
    document.recompute()
    state_before = _model_state(document)
    revision_before = _wildcard_revision(document)
    original_apply = body_create_module.apply_body_create

    def mutates_then_raises(admitted_document, body_name):
        original_apply(admitted_document, body_name)
        admitted_document.addObject("App::FeaturePython", "TransientSupport")
        anchor.Label = "Changed by rejected apply"
        raise RuntimeError("forced failure after structural effects")

    monkeypatch.setattr(body_create_module, "apply_body_create", mutates_then_raises)
    collaborators = _body_collaborators(FreeCAD, lambda _document: None)

    try:
        result = body_create_module.run_body_create(
            collaborators, document.Name, "RejectedBody"
        )

        assert result["success"] is False
        assert result["native_status"] == "ApplyFailed"
        assert result["committed"] is False
        assert document.getObject("RejectedBody") is None
        assert document.getObject("TransientSupport") is None
        assert _model_state(document) == state_before
        assert _wildcard_revision(document) == revision_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_body_create_native_recompute_failure_rolls_back(monkeypatch):
    _require_native_collaboration()

    import FreeCAD

    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import (
        body_create as body_create_module,
    )

    document = FreeCAD.newDocument("MCPBodyCreateNativeRecomputeFailure")

    class FailingRecomputeProbe:
        armed = False

        def execute(self, _object):
            if self.armed:
                self.armed = False
                raise RuntimeError("forced native recompute failure")

    proxy = FailingRecomputeProbe()
    probe = document.addObject("App::FeaturePython", "FailingRecomputeProbe")
    probe.Proxy = proxy
    document.recompute()
    state_before = _model_state(document)
    revision_before = _wildcard_revision(document)
    original_apply = body_create_module.apply_body_create

    def arm_recompute_failure(admitted_document, body_name):
        receipt = original_apply(admitted_document, body_name)
        proxy.armed = True
        probe.touch()
        return receipt

    monkeypatch.setattr(
        body_create_module, "apply_body_create", arm_recompute_failure
    )
    collaborators = _body_collaborators(FreeCAD, lambda _document: None)

    try:
        result = body_create_module.run_body_create(
            collaborators, document.Name, "RejectedBody"
        )

        assert result["success"] is False
        assert result["native_status"] == "RecomputeFailed"
        assert document.getObject("RejectedBody") is None
        assert _model_state(document) == state_before
        assert _wildcard_revision(document) == revision_before
    finally:
        proxy.armed = False
        FreeCAD.closeDocument(document.Name)


def test_body_create_native_rollback_failure_is_uncertain_and_fences_document(
    monkeypatch,
):
    _require_native_collaboration()

    import FreeCAD

    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import (
        body_create as body_create_module,
    )

    document = FreeCAD.newDocument("MCPBodyCreateNativeRollbackFailure")

    class PersistentFailureProbe:
        armed = False

        def execute(self, _object):
            if self.armed:
                raise RuntimeError("persistent recompute failure blocks restoration")

    proxy = PersistentFailureProbe()
    probe = document.addObject("App::FeaturePython", "PersistentFailureProbe")
    probe.Proxy = proxy
    document.recompute()
    original_apply = body_create_module.apply_body_create

    def arm_persistent_failure(admitted_document, body_name):
        receipt = original_apply(admitted_document, body_name)
        proxy.armed = True
        probe.touch()
        return receipt

    monkeypatch.setattr(
        body_create_module, "apply_body_create", arm_persistent_failure
    )
    collaborators = _body_collaborators(FreeCAD, lambda _document: None)

    try:
        result = body_create_module.run_body_create(
            collaborators, document.Name, "UncertainBody"
        )
        proxy.armed = False
        fenced = body_create_module.run_body_create(
            collaborators, document.Name, "MustNotApply"
        )

        assert result["success"] is False
        assert result["outcome"] == "uncertain"
        assert result["native_status"] == "RollbackFailed"
        assert result["rollback_succeeded"] is False
        assert result["retry_safe"] is False
        assert fenced["success"] is False
        assert fenced["native_status"] == "RollbackFailed"
        assert document.getObject("MustNotApply") is None
    finally:
        proxy.armed = False
        FreeCAD.closeDocument(document.Name)


def test_body_create_native_inspection_failure_rolls_back_after_recompute(monkeypatch):
    _require_native_collaboration()

    import FreeCAD

    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import (
        body_create as body_create_module,
    )

    document = FreeCAD.newDocument("MCPBodyCreateNativeInspectionFailure")
    state_before = _model_state(document)
    revision_before = _wildcard_revision(document)

    def reject_inspection(_document, _receipt):
        raise body_create_module.BodyCreateError(
            "CREATED_OBJECT_WRONG_TYPE", "forced post-recompute inspection failure"
        )

    monkeypatch.setattr(body_create_module, "read_body_result", reject_inspection)
    collaborators = _body_collaborators(FreeCAD, lambda _document: None)

    try:
        result = body_create_module.run_body_create(
            collaborators, document.Name, "RejectedBody"
        )

        assert result["success"] is False
        assert result["error_code"] == "CREATED_OBJECT_WRONG_TYPE"
        assert result["rollback_succeeded"] is True
        assert document.getObject("RejectedBody") is None
        assert _model_state(document) == state_before
        assert _wildcard_revision(document) == revision_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_body_create_native_failure_isolated_and_healthy_rollback_recovers():
    _require_native_collaboration()

    import FreeCAD

    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.body_create import (
        run_body_create,
    )

    failed_document = FreeCAD.newDocument("MCPBodyCreateIsolatedFailure")
    healthy_document = FreeCAD.newDocument("MCPBodyCreateHealthyDocument")
    rejected_names = {failed_document.Name}

    def validator(document):
        if document.Name in rejected_names:
            raise RuntimeError("document-local injected fault")

    collaborators = _body_collaborators(FreeCAD, validator)
    try:
        failed = run_body_create(
            collaborators, failed_document.Name, "InitiallyRejectedBody"
        )
        isolated = run_body_create(
            collaborators, healthy_document.Name, "HealthyBody"
        )
        rejected_names.clear()
        recovered = run_body_create(
            collaborators, failed_document.Name, "RecoveredBody"
        )

        assert failed["success"] is False
        assert failed_document.getObject("InitiallyRejectedBody") is None
        assert isolated["success"] is True
        assert healthy_document.getObject(isolated["body"]) is not None
        assert recovered["success"] is True
        assert failed_document.getObject(recovered["body"]) is not None
    finally:
        FreeCAD.closeDocument(failed_document.Name)
        FreeCAD.closeDocument(healthy_document.Name)
