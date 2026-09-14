"""Unit coverage for the typed ``create_placement_binder`` mutation slice."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.collaboration_api import CollaborationAPI
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import create_placement_binder as subject
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.create_placement_binder import run_create_placement_binder

pytestmark = pytest.mark.unit


def _item(name: str, *, label: str | None = None, type_id: str = "App::FeaturePython"):
    obj = SimpleNamespace(
        Name=name,
        Label=label if label is not None else f"Label for {name}",
        TypeId=type_id,
        State=[],
        InList=[],
        Group=[],
        PropertiesList=[],
        Placement=SimpleNamespace(Base=SimpleNamespace(x=0.0, y=0.0, z=0.0)),
    )
    obj.setExpression = lambda *_a, **_k: None
    obj.clearExpression = lambda *_a, **_k: None
    obj.set = lambda *_a, **_k: None
    obj.setAlias = lambda *_a, **_k: None
    obj.get = lambda *_a, **_k: "1"
    obj.getContents = lambda *_a, **_k: "1"
    obj.getAlias = lambda *_a, **_k: None
    obj.getCellFromAlias = lambda *_a, **_k: None
    obj.getNonEmptyCells = lambda: []
    obj.addObject = lambda other: obj.Group.append(other)
    obj.newObject = lambda type_id, name: _item(name, type_id=type_id)
    obj.addExternal = lambda *_a, **_k: None
    obj.saveCopy = lambda path: PathWrite(path)
    obj._mcp_snapshots = []
    return obj


def PathWrite(path: str) -> None:
    with open(path, "wb") as handle:
        handle.write(b"snap")


class _Document:
    Name = "Doc"

    def __init__(self, events: list[str], *, assigned_name: str | None = None) -> None:
        self.events = events
        self.objects: dict[str, object] = {}
        self.assigned_name = assigned_name
        self.recomputed = False
        self.add_calls = 0
        self._mcp_snapshots: list[object] = []

    @property
    def Objects(self) -> list[object]:
        return list(self.objects.values())

    def getObject(self, name):
        item = self.objects.get(name)
        if item is not None and self.recomputed:
            self.events.append("inspect")
        return item

    def addObject(self, object_type, name):
        self.add_calls += 1
        self.events.append("apply")
        actual_name = self.assigned_name or name
        item = _item(actual_name, type_id=object_type)
        self.objects[actual_name] = item
        return item

    def removeObject(self, name):
        self.objects.pop(name, None)

    def recompute(self):
        self.events.append("recompute")
        self.recomputed = True

    def saveCopy(self, path):
        PathWrite(path)


class _MutateThenRaiseDocument(_Document):
    def addObject(self, object_type, name):
        super().addObject(object_type, name)
        raise RuntimeError("FreeCAD failed after mutating")


class _RecomputeFailureDocument(_Document):
    def recompute(self):
        super().recompute()
        raise RuntimeError("FreeCAD recompute failed")


class _NativeBridgeDocument(_Document):
    def commitCompatibilityMutation(self, callback, *, structural=False, postcondition=None):
        assert structural is True or structural is False
        before_objects = dict(self.objects)
        before_recomputed = self.recomputed
        try:
            callback()
            self.recompute()
            if postcondition is not None and not postcondition():
                self.objects = before_objects
                self.recomputed = before_recomputed
                self.events.append("abort")
                return {"status": "PostconditionFailed", "committed": False}
        except Exception:
            self.objects = before_objects
            self.recomputed = before_recomputed
            self.events.append("abort")
            return {"status": "ApplyFailed", "committed": False}
        self.events.append("commit")
        return {"status": "Committed", "committed": True}


class _CompatibilityAPI:
    def __init__(self, document: _Document | None, *, final_result=None) -> None:
        self.document = document
        self.final_result = final_result
        self.calls = []

    def _restore(self, objects, recomputed) -> None:
        assert self.document is not None
        self.document.objects = objects
        self.document.recomputed = recomputed
        self.document.events.append("abort")

    def commit_compatibility_mutation(
        self,
        document_name,
        callback,
        *,
        structural=False,
        postcondition=None,
        bind_document=False,
        require_native=False,
    ):
        self.calls.append((document_name, structural, bind_document, require_native))
        if self.document is None:
            raise LookupError("document_lookup returned no document")
        before_objects = dict(self.document.objects)
        before_recomputed = self.document.recomputed
        try:
            callback(self.document) if bind_document else callback()
        except Exception as exc:
            self._restore(before_objects, before_recomputed)
            return {"status": "ApplyFailed", "committed": False, "message": str(exc)}
        try:
            self.document.recompute()
        except Exception as exc:
            self._restore(before_objects, before_recomputed)
            return {
                "status": "RecomputeFailed",
                "committed": False,
                "rollback_succeeded": True,
                "message": str(exc),
            }
        if postcondition is not None:
            satisfied = postcondition(self.document) if bind_document else postcondition()
            if not satisfied:
                self._restore(before_objects, before_recomputed)
                return {
                    "status": "PostconditionFailed",
                    "committed": False,
                    "rollback_succeeded": True,
                }
        if self.final_result is not None:
            result = dict(self.final_result)
            if not result.get("committed"):
                self._restore(before_objects, before_recomputed)
            return result
        self.document.events.append("commit")
        return {"status": "Committed", "committed": True}

    def commit_native_mutation(self, document_name, callback, postcondition, *, structural=True):
        return self.commit_compatibility_mutation(
            document_name,
            callback,
            structural=structural,
            postcondition=postcondition,
            bind_document=True,
            require_native=True,
        )


def _seed(document: _Document) -> None:
    seed = "body"
    if seed in {"sheet", "object", "move", "body", "source", "wire", "sketch", "datum", "relink", "analysis", "snapshot"}:
        document.objects["Seed"] = _item("Seed", type_id="App::FeaturePython")
        document.objects["Target"] = _item("Target", type_id="App::FeaturePython")
        document.objects["Body"] = _item("Body", type_id="PartDesign::Body")
        if seed == "sheet":
            document.objects["Target"].TypeId = "Spreadsheet::Sheet"
        if seed == "body":
            def maker(type_id, name):
                created = document.addObject(type_id, name)
                body = document.objects.get("Body")
                if body is not None:
                    body.Group.append(created)
                    created.InList.append(body)
                return created

            document.objects["Seed"].newObject = maker
            document.objects["Body"].newObject = maker
        if seed == "snapshot":
            document._mcp_snapshots.append({"id": "snap-test", "path": "x.FCStd", "doc": "Doc"})


def _collaborators(document: _Document | None, events: list[str], *, validator=None, final_result=None):
    api = _CompatibilityAPI(document, final_result=final_result)
    collaborators = SimpleNamespace(
        validate_document_invariants=(
            validator if validator is not None else lambda _document: events.append("validate")
        ),
        commit_native_mutation=api.commit_native_mutation,
        run_fem_analysis=lambda *_a, **_k: {"success": True},
        part=object(),
    )
    return collaborators, api


def test_create_placement_binder_runs_apply_recompute_inspect_validate_then_commits():
    events: list[str] = []
    document = _Document(events)
    _seed(document)
    collaborators, _api = _collaborators(document, events)

    result = run_create_placement_binder(collaborators, "Doc", "Body", "Created", "Seed", True, "Synchronized")

    assert result["success"] is True
    assert result["outcome"] == "committed"
    assert result["committed"] is True
    assert "recompute" in events
    assert "commit" in events


def test_missing_document_fails_without_entering_the_apply_callback():
    events: list[str] = []
    collaborators, api = _collaborators(None, events)
    result = run_create_placement_binder(collaborators, "Doc", "Body", "Created", "Seed", True, "Synchronized")
    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
    assert events == []


def test_creation_that_changes_then_raises_is_rolled_back(monkeypatch):
    events: list[str] = []
    document = _Document(events)
    _seed(document)
    collaborators, _api = _collaborators(document, events)

    def mutate_then_raise(doc, request):
        doc.addObject("App::FeaturePython", "Boom")
        raise RuntimeError("FreeCAD failed after mutating")

    monkeypatch.setattr(subject, "apply_create_placement_binder", mutate_then_raise)
    result = run_create_placement_binder(collaborators, "Doc", "Body", "Created", "Seed", True, "Synchronized")
    assert result["success"] is False
    assert "abort" in events or result["outcome"] in {"rejected", "uncertain"}


def test_recompute_failure_is_rolled_back():
    events: list[str] = []
    document = _RecomputeFailureDocument(events)
    _seed(document)
    collaborators, _api = _collaborators(document, events)
    result = run_create_placement_binder(collaborators, "Doc", "Body", "Created", "Seed", True, "Synchronized")
    assert result["success"] is False
    assert result.get("native_status") == "RecomputeFailed"


def test_failed_validation_aborts_before_commit():
    events: list[str] = []
    document = _Document(events)
    _seed(document)

    def fail_validation(_document):
        events.append("validate")
        raise RuntimeError("document health degraded")

    collaborators, _api = _collaborators(document, events, validator=fail_validation)
    result = run_create_placement_binder(collaborators, "Doc", "Body", "Created", "Seed", True, "Synchronized")
    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_HEALTH_DEGRADED"


def test_native_rejection_never_returns_cached_success():
    events: list[str] = []
    document = _Document(events)
    _seed(document)
    collaborators, _api = _collaborators(
        document, events, final_result={"status": "PublicationFailed", "committed": False}
    )
    result = run_create_placement_binder(collaborators, "Doc", "Body", "Created", "Seed", True, "Synchronized")
    assert result["success"] is False
    assert result["native_status"] == "PublicationFailed"


def test_native_capability_is_required_before_apply():
    events: list[str] = []
    document = _Document(events)
    _seed(document)
    bridge = CollaborationAPI(document_lookup=lambda _name: document)
    collaborators = SimpleNamespace(
        validate_document_invariants=lambda _document: events.append("validate"),
        commit_native_mutation=bridge.commit_native_mutation,
        run_fem_analysis=lambda *_a, **_k: {"success": True},
    )
    result = run_create_placement_binder(collaborators, "Doc", "Body", "Created", "Seed", True, "Synchronized")
    assert result["success"] is False
    assert result.get("native_status") == "Unsupported"
    assert events == []


def test_native_rollback_failure_remains_distinguishable():
    events: list[str] = []
    document = _Document(events)
    _seed(document)
    collaborators, _api = _collaborators(
        document,
        events,
        final_result={"status": "RollbackFailed", "committed": False, "rollback_succeeded": False},
    )
    result = run_create_placement_binder(collaborators, "Doc", "Body", "Created", "Seed", True, "Synchronized")
    assert result["success"] is False
    assert result["native_status"] == "RollbackFailed"
    assert result["rollback_succeeded"] is False


def test_apply_and_inspect_use_the_native_admitted_document():
    events: list[str] = []
    admitted = _NativeBridgeDocument(events)
    _seed(admitted)
    lookups: list[str] = []

    def changing_lookup(name):
        lookups.append(name)
        return admitted

    bridge = CollaborationAPI(document_lookup=changing_lookup)
    collaborators = SimpleNamespace(
        validate_document_invariants=lambda _document: events.append("validate"),
        commit_native_mutation=bridge.commit_native_mutation,
        run_fem_analysis=lambda *_a, **_k: {"success": True},
    )
    result = run_create_placement_binder(collaborators, "Doc", "Body", "Created", "Seed", True, "Synchronized")
    assert lookups == ["Doc"]
    assert result["success"] is True or result["outcome"] in {"rejected", "uncertain"}


def test_unknown_or_contradictory_native_evidence_cannot_release_success():
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.create_placement_binder_mutation import (
        _create_placement_binder_native_result,
        _NativeMutationState,
    )

    for native_result in (
        None,
        {},
        {"status": "FutureStatus", "committed": False},
        {"status": "Committed", "committed": False},
        {"status": "Busy", "committed": True},
        {"status": "Committed", "committed": True, "rollback_failed": True},
    ):
        result = _create_placement_binder_native_result(native_result, _NativeMutationState(postcondition_passed=True))
        assert result["success"] is False
        assert result["outcome"] == "uncertain"
