from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server import rpc_server as addon_rpc
from addon.FreeCADMCP.rpc_server.mutation_guard import (
    DocumentHealthVerdict,
    GuiMutationTransaction,
    RollbackCoverage,
    ValidationProfile,
    calculate_document_health_delta,
    capture_document_health,
    make_method_spec,
)


pytestmark = pytest.mark.unit


class Shape:
    def __init__(self, code=1, *, null=False, valid=True):
        self.code = code
        self.null = null
        self.valid = valid

    def hashCode(self):
        return self.code

    def isNull(self):
        return self.null

    def isValid(self):
        return self.valid


class CountingShape(Shape):
    null_checks = 0
    validity_checks = 0

    def isNull(self):
        type(self).null_checks += 1
        return super().isNull()

    def isValid(self):
        type(self).validity_checks += 1
        return super().isValid()


class Obj:
    def __init__(self, name, *, state=(), shape=None, type_id="Part::Feature"):
        self.Name = name
        self.Label = name
        self.State = list(state)
        self.Shape = shape
        self.TypeId = type_id
        self.Touched = False
        self.Placement = None
        self.Group = []
        self.Tip = None

    def isDerivedFrom(self, type_name):
        return self.TypeId == type_name


class Doc:
    def __init__(self, name="Model", objects=()):
        self.Name = name
        self.Objects = list(objects)
        self.Modified = False
        self.opened = 0
        self.commits = 0
        self.aborts = 0
        self.fail_abort = False

    def openTransaction(self, _name):
        self.opened += 1

    def commitTransaction(self):
        self.commits += 1

    def abortTransaction(self):
        self.aborts += 1
        if self.fail_abort:
            raise RuntimeError("rollback failed")

    def recompute(self):
        return True


class UndoModeDoc(Doc):
    def __init__(self, name="Model", objects=()):
        super().__init__(name, objects)
        self.UndoMode = 0
        self.modes_during_open = []

    def openTransaction(self, name):
        self.modes_during_open.append(self.UndoMode)
        super().openTransaction(name)


def test_health_delta_separates_preexisting_and_new_errors():
    stable = Obj("Stable", state=("Error",), shape=Shape(1))
    created = Obj("Created", shape=Shape(2))
    doc = Doc(objects=(stable,))
    before = capture_document_health(
        doc, profile=ValidationProfile.DEFAULT, affected_objects=("Stable",)
    )
    doc.Objects.append(created)
    after = capture_document_health(
        doc, profile=ValidationProfile.DEFAULT, affected_objects=("Created",)
    )
    delta = calculate_document_health_delta(
        before, after, expected_modified_objects=("Created",)
    )

    assert delta.verdict == DocumentHealthVerdict.WARNING
    assert delta.preexisting_recompute_errors == ("Stable",)
    assert delta.new_recompute_errors == ()
    assert delta.created_objects == ("Created",)


def test_new_invalid_shape_and_broken_body_tip_degrade_health():
    feature = Obj("Feature", shape=Shape(1))
    body = Obj("Body", type_id="PartDesign::Body")
    body.Group = [feature]
    body.Tip = feature
    doc = Doc(objects=(feature, body))
    before = capture_document_health(
        doc, profile=ValidationProfile.FULL, affected_objects=("Feature",)
    )
    feature.Shape = Shape(2, null=True, valid=False)
    body.Tip = Obj("Foreign")
    after = capture_document_health(
        doc, profile=ValidationProfile.FULL, affected_objects=("Feature",)
    )
    delta = calculate_document_health_delta(
        before, after, expected_modified_objects=("Feature",)
    )

    assert delta.verdict == DocumentHealthVerdict.DEGRADED
    assert delta.new_null_shapes == ("Feature",)
    assert delta.body_tip_issues == ("Body.Tip",)


def test_none_profile_reports_unknown_and_default_detects_unexpected_change():
    obj = Obj("Feature", shape=Shape(1))
    doc = Doc(objects=(obj,))
    skipped = capture_document_health(doc, profile=ValidationProfile.NONE)
    assert skipped.validation_available is False
    assert (
        calculate_document_health_delta(skipped, skipped).verdict
        == DocumentHealthVerdict.UNKNOWN
    )

    before = capture_document_health(doc, profile=ValidationProfile.DEFAULT)
    obj.Label = "Changed"
    after = capture_document_health(doc, profile=ValidationProfile.DEFAULT)
    delta = calculate_document_health_delta(before, after)
    assert delta.verdict == DocumentHealthVerdict.WARNING
    assert delta.unexpected_modified_objects == ("Feature",)


def test_default_health_validation_bounds_expensive_shape_checks_to_affected_objects():
    CountingShape.null_checks = 0
    CountingShape.validity_checks = 0
    objects = tuple(
        Obj(f"Feature{index}", shape=CountingShape(index + 1))
        for index in range(200)
    )
    capture_document_health(
        Doc(objects=objects),
        profile=ValidationProfile.DEFAULT,
        affected_objects=("Feature57",),
    )
    assert CountingShape.null_checks == 1
    assert CountingShape.validity_checks == 1


def test_transaction_reports_commit_abort_multi_document_and_rollback_failure():
    first, second = Doc("First"), Doc("Second")
    with GuiMutationTransaction(
        (first, second), "commit", enabled=True
    ) as committed:
        pass
    assert committed.to_dict(coverage=RollbackCoverage.DOCUMENT_ONLY) == {
        "status": "committed",
        "enabled": True,
        "documents": ["First", "Second"],
        "started": True,
        "committed": True,
        "abort_attempted": False,
        "abort_succeeded": None,
        "abort_errors": [],
        "rollback_attempted": False,
        "rollback_succeeded": None,
        "coverage": "document_only",
    }
    assert first.commits == second.commits == 1

    failed = Doc("Failed")
    failed.fail_abort = True
    with GuiMutationTransaction((failed,), "abort", enabled=True) as transaction:
        assert transaction.abort() is False
    report = transaction.to_dict()
    assert report["status"] == "rollback_failed"
    assert report["abort_succeeded"] is False
    assert report["abort_errors"][0]["document"] == "Failed"


def test_transaction_enables_and_restores_headless_undo_recording():
    document = UndoModeDoc()
    with GuiMutationTransaction(
        (document,), "headless", enabled=True
    ) as transaction:
        assert document.UndoMode == 1
        transaction.abort()
    assert document.modes_during_open == [1]
    assert document.UndoMode == 0
    assert transaction.abort_succeeded is True


def test_mutation_validator_failure_aborts_before_commit(monkeypatch):
    feature = Obj("Feature", shape=Shape(1))
    document = Doc(objects=(feature,))
    monkeypatch.setattr(
        addon_rpc,
        "FreeCAD",
        SimpleNamespace(
            listDocuments=lambda: {"Model": document},
        ),
    )
    spec = replace(
        make_method_spec("create_object", "MUTATING"),
        validator=lambda _doc: (_ for _ in ()).throw(RuntimeError("invalid")),
    )
    result, failed = addon_rpc.FreeCADRPC()._execute_mutation_with_health(
        lambda: {"success": True, "object_name": "Feature"},
        (document,),
        spec,
        expected_objects=("Feature",),
        request_id="request",
    )

    assert failed is True
    assert document.commits == 0
    assert document.aborts == 1
    assert result["transaction"]["status"] == "aborted"
    assert result["document_health"]["validation_error"].startswith("RuntimeError")


def _install_documents(monkeypatch, *documents):
    by_name = {document.Name: document for document in documents}
    monkeypatch.setattr(
        addon_rpc,
        "FreeCAD",
        SimpleNamespace(
            listDocuments=lambda: dict(by_name),
            getDocument=by_name.get,
        ),
    )


def test_healthy_typed_mutation_commits_with_expected_object_delta(monkeypatch):
    feature = Obj("Feature", shape=Shape(1))
    document = Doc(objects=(feature,))
    _install_documents(monkeypatch, document)
    spec = make_method_spec("edit_object", "MUTATING")

    def mutate():
        feature.Label = "Expected label"
        return {"success": True, "object_name": feature.Name}

    result, failed = addon_rpc.FreeCADRPC()._execute_mutation_with_health(
        mutate,
        (document,),
        spec,
        expected_objects=("Feature",),
    )
    assert failed is False
    assert result["transaction"]["status"] == "committed"
    assert result["document_health"]["verdict"] == "healthy"
    assert result["document_health"]["modified_objects"] == ["Model.Feature"]


def test_backend_failure_and_new_invalid_shape_abort_before_commit(monkeypatch):
    feature = Obj("Feature", shape=Shape(1))
    document = Doc(objects=(feature,))
    _install_documents(monkeypatch, document)
    spec = make_method_spec("edit_object", "MUTATING")
    rpc = addon_rpc.FreeCADRPC()

    failed_result, failed = rpc._execute_mutation_with_health(
        lambda: {
            "success": False,
            "error_code": "PROPERTY_REJECTED",
            "error": "invalid property",
        },
        (document,),
        spec,
        expected_objects=("Feature",),
    )
    assert failed is True
    assert failed_result["transaction"]["status"] == "aborted"

    feature.Shape = Shape(1)

    def degrade():
        feature.Shape = Shape(2, null=True, valid=False)
        return {"success": True, "object_name": feature.Name}

    degraded, failed = rpc._execute_mutation_with_health(
        degrade,
        (document,),
        spec,
        expected_objects=("Feature",),
    )
    assert failed is True
    assert degraded["error_code"] == "DOCUMENT_HEALTH_DEGRADED"
    assert degraded["transaction"]["status"] == "aborted"
    assert degraded["document_health"]["attempted_verdict"] == "degraded"


def test_unrelated_document_mutation_is_degraded_and_rolled_back(monkeypatch):
    target = Doc("Target", objects=(Obj("TargetFeature", shape=Shape(1)),))
    unrelated_obj = Obj("Unrelated", shape=Shape(2))
    unrelated = Doc("UnrelatedDoc", objects=(unrelated_obj,))
    _install_documents(monkeypatch, target, unrelated)
    spec = make_method_spec("edit_object", "MUTATING")

    def mutate_wrong_document():
        unrelated_obj.Label = "unexpected"
        return {"success": True, "object_name": "TargetFeature"}

    result, failed = addon_rpc.FreeCADRPC()._execute_mutation_with_health(
        mutate_wrong_document,
        (target,),
        spec,
        expected_objects=("TargetFeature",),
    )
    assert failed is True
    assert result["document_health"]["unexpected_modified_documents"] == [
        "UnrelatedDoc"
    ]
    assert result["transaction"]["status"] == "aborted"


def test_public_execute_reports_unavailable_outer_rollback_coverage(monkeypatch):
    document = Doc(objects=(Obj("Feature", shape=Shape(1)),))
    _install_documents(monkeypatch, document)
    spec = make_method_spec("execute_code", "MUTATING")
    result, failed = addon_rpc.FreeCADRPC()._execute_mutation_with_health(
        lambda: {"success": True},
        (document,),
        spec,
    )
    assert failed is False
    assert result["transaction"]["enabled"] is False
    assert result["transaction"]["coverage"] == "unavailable"
    assert result["mutation_scope"]["transaction_coverage"] == "unavailable"
    assert result["mutation_scope"]["rollback_policy"] == "none"
