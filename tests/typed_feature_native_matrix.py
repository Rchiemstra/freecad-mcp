"""Shared native qualification matrix used by per-op test_native_*.py files."""

from __future__ import annotations

import hashlib
import importlib
import os
from types import SimpleNamespace

import pytest

from tests.typed_feature_native_setup import prepare_native_document, run_kwargs


def require_native_collaboration() -> None:
    if os.environ.get("FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION") != "1":
        pytest.skip("Compose FreeCAD is adapter-only; use the branch-built lane")
    import FreeCAD

    if getattr(FreeCAD, "__mcp_test_stub__", False):
        raise RuntimeError("Native qualification requires a real branch-built FreeCAD")


def _property_content(item, name: str):
    if name == "Proxy":
        proxy = getattr(item, "Proxy", None)
        if proxy is None:
            return None
        return f"{type(proxy).__module__}.{type(proxy).__qualname__}"
    dumped = bytes(item.dumpPropertyContent(name, 0))
    return hashlib.sha256(dumped).hexdigest()


def model_state(document):
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


def revision_state(document, op: str):
    keys = [{"kind": "UnknownModelMutation"}, {"kind": "DocumentStructure"}]
    names = {item.Name for item in document.Objects} | {"RejectedFeature", "TransientSupport"}
    for name in sorted(names):
        keys.extend(
            {"kind": kind, "subject": name} for kind in ("ObjectExistence", "ObjectStructure")
        )
        item = document.getObject(name)
        if item is not None:
            keys.extend(
                {"kind": "ObjectProperty", "subject": name, "property_name": prop}
                for prop in sorted(item.PropertiesList)
            )
    session = document.beginEditSession(f"{op}-native-state-probe")
    try:
        snapshot = document.snapshotForEdit(session["session_id"], keys)
        return snapshot["revisions"]
    finally:
        document.cancelEdit(session["session_id"])


def collaborators(FreeCAD, validator):
    from addon.FreeCADMCP.collaboration_api import CollaborationAPI

    bridge = CollaborationAPI(document_lookup=FreeCAD.getDocument)
    return SimpleNamespace(
        validate_document_invariants=validator,
        commit_native_mutation=bridge.commit_native_mutation,
    )


def load_subject(op: str):
    return importlib.import_module(
        f"addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.{op}"
    )


def invoke(subject, collab, document_name: str, base: dict[str, object], **overrides):
    payload = run_kwargs(base, document_name, overrides)
    return subject.run_fn(collab, **payload) if hasattr(subject, "run_fn") else getattr(
        subject, f"run_{subject.__name__.rsplit('.', 1)[-1]}"
    )(collab, **payload)


def _run(op: str, collab, document_name: str, base: dict[str, object], **overrides):
    subject = load_subject(op)
    runner = getattr(subject, f"run_{op}")
    return runner(collab, **run_kwargs(base, document_name, overrides))


def check_success(op: str, kind: str, base: dict[str, object], monkeypatch) -> None:
    require_native_collaboration()
    import FreeCAD

    subject = load_subject(op)
    document = FreeCAD.newDocument(f"MCP{op}NativePhaseOrder")
    events: list[str] = []

    class RecomputeProbe:
        def execute(self, _object):
            events.append("recompute")

    try:
        prepare_native_document(document, kind)
        probe = document.addObject("App::FeaturePython", "RecomputeProbe")
        probe.Proxy = RecomputeProbe()
        document.recompute()
        events.clear()
        original_apply = getattr(subject, f"apply_{op}")
        original_read = getattr(subject, f"read_{op}_result")

        def tracked_apply(admitted_document, request):
            events.append("apply")
            probe.touch()
            return original_apply(admitted_document, request)

        def tracked_read(admitted_document, receipt):
            events.append("inspect")
            return original_read(admitted_document, receipt)

        monkeypatch.setattr(subject, f"apply_{op}", tracked_apply)
        monkeypatch.setattr(subject, f"read_{op}_result", tracked_read)
        result = _run(
            op,
            collaborators(FreeCAD, lambda _document: events.append("validate")),
            document.Name,
            base,
        )
        assert result["success"] is True
        assert result["committed"] is True
        assert events == ["apply", "recompute", "inspect", "validate"]
        assert document.getObject(result["feature"]) is not None
    finally:
        FreeCAD.closeDocument(document.Name)


def check_validation_failure(op: str, kind: str, base: dict[str, object]) -> None:
    require_native_collaboration()
    import FreeCAD

    document = FreeCAD.newDocument(f"MCP{op}NativeRollback")
    try:
        prepare_native_document(document, kind)
        document.recompute()
        before = model_state(document), revision_state(document, op)
        result = _run(
            op,
            collaborators(
                FreeCAD,
                lambda _document: (_ for _ in ()).throw(RuntimeError("forced validation failure")),
            ),
            document.Name,
            base,
        )
        assert result["success"] is False
        assert result["error_code"] == "DOCUMENT_HEALTH_DEGRADED"
        assert result["rollback_succeeded"] is True
        assert (model_state(document), revision_state(document, op)) == before
    finally:
        FreeCAD.closeDocument(document.Name)


def check_apply_failure(op: str, kind: str, base: dict[str, object], monkeypatch) -> None:
    require_native_collaboration()
    import FreeCAD

    subject = load_subject(op)
    document = FreeCAD.newDocument(f"MCP{op}NativeApplyFailure")
    try:
        prepare_native_document(document, kind)
        anchor = document.addObject("App::FeaturePython", "ExistingAnchor")
        anchor.Label = "Before"
        document.recompute()
        before = model_state(document), revision_state(document, op)
        original_apply = getattr(subject, f"apply_{op}")

        def mutates_then_raises(admitted_document, request):
            original_apply(admitted_document, request)
            admitted_document.addObject("App::FeaturePython", "TransientSupport")
            anchor.Label = "Changed by rejected apply"
            raise RuntimeError("forced failure after structural effects")

        monkeypatch.setattr(subject, f"apply_{op}", mutates_then_raises)
        result = _run(op, collaborators(FreeCAD, lambda _document: None), document.Name, base)
        assert result["success"] is False
        assert result["native_status"] == "ApplyFailed"
        assert document.getObject("TransientSupport") is None
        assert (model_state(document), revision_state(document, op)) == before
    finally:
        FreeCAD.closeDocument(document.Name)


def check_recompute_failure(op: str, kind: str, base: dict[str, object], monkeypatch) -> None:
    require_native_collaboration()
    import FreeCAD

    subject = load_subject(op)
    document = FreeCAD.newDocument(f"MCP{op}NativeRecomputeFailure")

    class FailingRecomputeProbe:
        armed = False

        def execute(self, _object):
            if self.armed:
                self.armed = False
                raise RuntimeError("forced native recompute failure")

    proxy = FailingRecomputeProbe()
    try:
        prepare_native_document(document, kind)
        probe = document.addObject("App::FeaturePython", "FailingRecomputeProbe")
        probe.Proxy = proxy
        document.recompute()
        before = model_state(document), revision_state(document, op)
        original_apply = getattr(subject, f"apply_{op}")

        def arm_recompute_failure(admitted_document, request):
            receipt = original_apply(admitted_document, request)
            proxy.armed = True
            probe.touch()
            return receipt

        monkeypatch.setattr(subject, f"apply_{op}", arm_recompute_failure)
        result = _run(op, collaborators(FreeCAD, lambda _document: None), document.Name, base)
        assert result["success"] is False
        assert result["native_status"] == "RecomputeFailed"
        assert (model_state(document), revision_state(document, op)) == before
    finally:
        proxy.armed = False
        FreeCAD.closeDocument(document.Name)


def check_rollback_failure_fences(op: str, kind: str, base: dict[str, object], monkeypatch) -> None:
    require_native_collaboration()
    import FreeCAD

    subject = load_subject(op)
    document = FreeCAD.newDocument(f"MCP{op}NativeRollbackFailure")

    class PersistentFailureProbe:
        armed = False

        def execute(self, _object):
            if self.armed:
                raise RuntimeError("persistent recompute failure blocks restoration")

    proxy = PersistentFailureProbe()
    try:
        prepare_native_document(document, kind)
        probe = document.addObject("App::FeaturePython", "PersistentFailureProbe")
        probe.Proxy = proxy
        document.recompute()
        original_apply = getattr(subject, f"apply_{op}")

        def arm_persistent_failure(admitted_document, request):
            receipt = original_apply(admitted_document, request)
            proxy.armed = True
            probe.touch()
            return receipt

        monkeypatch.setattr(subject, f"apply_{op}", arm_persistent_failure)
        collab = collaborators(FreeCAD, lambda _document: None)
        result = _run(op, collab, document.Name, base)
        proxy.armed = False
        fenced = _run(op, collab, document.Name, base, **{next(iter(base)): base[next(iter(base))]})
        del fenced
        fenced_result = _run(op, collab, document.Name, base)
        assert result["outcome"] == "uncertain"
        assert result["native_status"] == "RollbackFailed"
        assert result["rollback_succeeded"] is False
        assert fenced_result["native_status"] == "RollbackFailed"
    finally:
        proxy.armed = False
        FreeCAD.closeDocument(document.Name)


def check_inspection_failure(op: str, kind: str, base: dict[str, object], monkeypatch) -> None:
    require_native_collaboration()
    import FreeCAD

    subject = load_subject(op)
    error_cls = getattr(subject, f"{_pascal(op)}Error")
    document = FreeCAD.newDocument(f"MCP{op}NativeInspectionFailure")
    try:
        prepare_native_document(document, kind)
        document.recompute()
        before = model_state(document), revision_state(document, op)

        def reject_inspection(_document, _receipt):
            raise error_cls("CREATED_OBJECT_WRONG_TYPE", "forced post-recompute inspection failure")

        monkeypatch.setattr(subject, f"read_{op}_result", reject_inspection)
        result = _run(op, collaborators(FreeCAD, lambda _document: None), document.Name, base)
        assert result["success"] is False
        assert result["error_code"] == "CREATED_OBJECT_WRONG_TYPE"
        assert result["rollback_succeeded"] is True
        assert (model_state(document), revision_state(document, op)) == before
    finally:
        FreeCAD.closeDocument(document.Name)


def _pascal(op: str) -> str:
    return "".join(part.title() for part in op.split("_"))


def check_isolated_recovery(op: str, kind: str, base: dict[str, object], created_field: str) -> None:
    require_native_collaboration()
    import FreeCAD

    failed_document = FreeCAD.newDocument(f"MCP{op}IsolatedFailure")
    healthy_document = FreeCAD.newDocument(f"MCP{op}HealthyDocument")
    rejected_names = {failed_document.Name}

    def validator(document):
        if document.Name in rejected_names:
            raise RuntimeError("document-local injected fault")

    collab = collaborators(FreeCAD, validator)
    try:
        prepare_native_document(failed_document, kind)
        prepare_native_document(healthy_document, kind)
        failed_document.recompute()
        healthy_document.recompute()
        failed = _run(op, collab, failed_document.Name, base)
        isolated = _run(op, collab, healthy_document.Name, base)
        rejected_names.clear()
        recovered = _run(
            op,
            collab,
            failed_document.Name,
            base,
            **{created_field: "RecoveredFeature"},
        )
        assert failed["success"] is False
        assert isolated["success"] is True
        assert recovered["success"] is True
        assert healthy_document.getObject(isolated["feature"]) is not None
        assert failed_document.getObject(recovered["feature"]) is not None
    finally:
        FreeCAD.closeDocument(failed_document.Name)
        FreeCAD.closeDocument(healthy_document.Name)


def check_duplicate_and_missing(op: str, kind: str, base: dict[str, object]) -> None:
    require_native_collaboration()
    import FreeCAD

    document = FreeCAD.newDocument(f"MCP{op}TypedErrors")
    collab = collaborators(FreeCAD, lambda _: None)
    try:
        prepare_native_document(document, kind)
        document.recompute()
        first = _run(op, collab, document.Name, base)
        assert first["success"] is True
        before = model_state(document), revision_state(document, op)
        result = _run(op, collab, document.Name, base)
        assert result["error_code"] == "OBJECT_ALREADY_EXISTS"
        assert result["native_status"] == "ApplyFailed"
        assert (model_state(document), revision_state(document, op)) == before
        missing = _run(op, collab, "NoSuchFeatureQualificationDocument", base)
        assert missing["error_code"] == "DOCUMENT_NOT_FOUND"
        assert missing["outcome"] == "rejected"
    finally:
        FreeCAD.closeDocument(document.Name)


def check_rich_model_restore(
    op: str, kind: str, base: dict[str, object], monkeypatch, stage: str
) -> None:
    require_native_collaboration()
    import FreeCAD
    import Part

    subject = load_subject(op)
    error_cls = getattr(subject, f"{_pascal(op)}Error")
    document = FreeCAD.newDocument(f"MCP{op}RichRollback")
    try:
        prepare_native_document(document, kind)
        body = document.getObject("Body")
        if body is None:
            body = document.addObject("PartDesign::Body", "ExistingBody")
        feature = body.newObject("PartDesign::Feature", "Anchor")
        feature.Shape = Part.makeBox(2, 3, 4)
        feature.addProperty("App::PropertyFloat", "ReviewValue")
        feature.ReviewValue = 7
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
        document.recompute()
        before = model_state(document), revision_state(document, op)
        original_apply = getattr(subject, f"apply_{op}")
        original_inspect = getattr(subject, f"read_{op}_result")

        def change_model(admitted, request):
            receipt = original_apply(admitted, request)
            support = admitted.addObject("PartDesign::Feature", "TransientSupport")
            body.addObject(support)
            body.Tip = support
            feature.Label = "Changed"
            if stage == "apply":
                raise RuntimeError("injected rich-model apply failure")
            if stage == "recompute":
                proxy.armed = True
                probe.touch()
            return receipt

        def inspect(admitted, receipt):
            if stage == "inspection":
                raise error_cls("INSPECTION_FAILED", "injected inspection failure")
            return original_inspect(admitted, receipt)

        def validate(_document):
            if stage == "validation":
                raise RuntimeError("injected rich-model validation failure")

        monkeypatch.setattr(subject, f"apply_{op}", change_model)
        monkeypatch.setattr(subject, f"read_{op}_result", inspect)
        result = _run(op, collaborators(FreeCAD, validate), document.Name, base)
        assert result["outcome"] == "rejected"
        assert result["rollback_succeeded"] is True
        assert (model_state(document), revision_state(document, op)) == before
    finally:
        FreeCAD.closeDocument(document.Name)


def check_postcondition_cannot_write(
    op: str, kind: str, base: dict[str, object], write: str
) -> None:
    require_native_collaboration()
    import FreeCAD

    document = FreeCAD.newDocument(f"MCP{op}ReadOnlyPostcondition")
    try:
        prepare_native_document(document, kind)
        anchor = document.addObject("App::FeaturePython", "Anchor")
        document.recompute()
        before = model_state(document), revision_state(document, op)

        def validate(admitted):
            if write == "property":
                anchor.Label = "Unvalidated change"
            else:
                admitted.addObject("App::FeaturePython", "UnvalidatedObject")

        result = _run(op, collaborators(FreeCAD, validate), document.Name, base)
        assert result["outcome"] == "rejected"
        assert result["native_status"] == "PostconditionFailed"
        assert (model_state(document), revision_state(document, op)) == before
    finally:
        FreeCAD.closeDocument(document.Name)
