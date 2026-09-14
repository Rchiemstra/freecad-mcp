"""Unit coverage for the typed ``body_create`` mutation slice."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from addon.FreeCADMCP.collaboration_api import CollaborationAPI
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import body_create as subject
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.body_create import (
    run_body_create,
)

pytestmark = pytest.mark.unit


def _body(name: str, *, label: str | None = None, type_id: str = "PartDesign::Body"):
    return SimpleNamespace(
        Name=name,
        Label=label if label is not None else f"Label for {name}",
        TypeId=type_id,
    )


class _Document:
    Name = "Doc"

    def __init__(self, events: list[str], *, assigned_name: str | None = None) -> None:
        self.events = events
        self.objects: dict[str, Any] = {}
        self.assigned_name = assigned_name
        self.recomputed = False
        self.add_calls = 0

    def getObject(self, name):
        body = self.objects.get(name)
        if body is not None and self.recomputed:
            self.events.append("inspect")
        return body

    def addObject(self, object_type, name):
        self.add_calls += 1
        assert object_type == "PartDesign::Body"
        self.events.append("apply")
        actual_name = self.assigned_name or name
        body = _body(actual_name)
        self.objects[actual_name] = body
        return body

    def recompute(self):
        self.events.append("recompute")
        self.recomputed = True


class _MissingAfterRecomputeDocument(_Document):
    def recompute(self):
        super().recompute()
        self.objects.clear()


class _ReplacingAfterRecomputeDocument(_Document):
    def recompute(self):
        super().recompute()
        self.objects["Body"] = _body("Body", label="Replacement")


class _WrongTypeAfterRecomputeDocument(_Document):
    def recompute(self):
        super().recompute()
        self.objects["Body"].TypeId = "Part::Feature"


class _MutateThenRaiseDocument(_Document):
    def addObject(self, object_type, name):
        super().addObject(object_type, name)
        raise RuntimeError("FreeCAD failed after creating the Body")


class _RecomputeFailureDocument(_Document):
    def recompute(self):
        super().recompute()
        raise RuntimeError("FreeCAD recompute failed")


class _NativeBridgeDocument(_Document):
    """Document-shaped native binding used through the production bridge."""

    def commitCompatibilityMutation(self, callback, *, structural=False, postcondition=None):
        assert structural is True
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
    """Stand-in modeling every native phase used by Body creation."""

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

    def commit_body_create_mutation(self, document_name, callback, postcondition):
        return self.commit_compatibility_mutation(
            document_name,
            callback,
            structural=True,
            postcondition=postcondition,
            bind_document=True,
            require_native=True,
        )


def _collaborators(
    document: _Document | None,
    events: list[str],
    *,
    validator=None,
    final_result=None,
    freecad=None,
):
    if freecad is None:
        freecad = SimpleNamespace(
            getDocument=lambda name: (
                document if document is not None and name == document.Name else None
            )
        )
    api = _CompatibilityAPI(document, final_result=final_result)
    collaborators = SimpleNamespace(
        freecad=freecad,
        validate_document_invariants=(
            validator if validator is not None else lambda _document: events.append("validate")
        ),
        commit_body_create_mutation=api.commit_body_create_mutation,
    )
    return collaborators, api


def test_body_create_runs_apply_recompute_inspect_validate_then_commits():
    events = []
    document = _Document(events)
    collaborators, api = _collaborators(document, events)

    result = run_body_create(collaborators, "Doc", "Body")

    assert result == {
        "contract_version": 1,
        "success": True,
        "ok": True,
        "outcome": "committed",
        "committed": True,
        "retry_safe": False,
        "body": "Body",
        "label": "Label for Body",
    }
    assert events == ["apply", "recompute", "inspect", "validate", "commit"]
    assert api.calls == [("Doc", True, True, True)]


@pytest.mark.parametrize("body_name", [None, 42, [], {}, "", " ", "\t\r\n"])
def test_invalid_names_abort_without_recompute_or_commit(body_name):
    events = []
    document = _Document(events)
    collaborators, _api = _collaborators(document, events)

    result = run_body_create(collaborators, "Doc", body_name)

    assert result["success"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"
    assert document.objects == {}
    assert "recompute" not in events
    assert "commit" not in events


def test_missing_document_fails_without_entering_the_apply_callback():
    events = []
    collaborators, api = _collaborators(None, events)

    result = run_body_create(collaborators, "Missing", "Body")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
    assert api.calls == [("Missing", True, True, True)]
    assert events == []


def test_duplicate_name_aborts_without_recompute_or_commit():
    events = []
    document = _Document(events)
    existing = _body("Body", label="Existing")
    document.objects["Body"] = existing
    collaborators, _api = _collaborators(document, events)

    result = run_body_create(collaborators, "Doc", "Body")

    assert result["success"] is False
    assert result["error_code"] == "OBJECT_ALREADY_EXISTS"
    assert document.objects == {"Body": existing}
    assert "recompute" not in events
    assert "commit" not in events


def test_creation_that_changes_then_raises_is_rolled_back():
    events = []
    document = _MutateThenRaiseDocument(events)
    collaborators, _api = _collaborators(document, events)

    result = run_body_create(collaborators, "Doc", "Body")

    assert result["success"] is False
    assert result["error_code"] == "BODY_CREATE_FAILED"
    assert document.objects == {}
    assert events == ["apply", "abort"]


def test_recompute_failure_is_rolled_back():
    events = []
    document = _RecomputeFailureDocument(events)
    collaborators, _api = _collaborators(document, events)

    result = run_body_create(collaborators, "Doc", "Body")

    assert result["success"] is False
    assert result["error_code"] == "NATIVE_COMPATIBILITY_MUTATION_REJECTED"
    assert result["native_status"] == "RecomputeFailed"
    assert result["rollback_succeeded"] is True
    assert document.objects == {}
    assert events == ["apply", "recompute", "abort"]


def test_failed_validation_aborts_before_commit():
    events = []
    document = _Document(events)

    def fail_validation(_document):
        events.append("validate")
        raise RuntimeError("document health degraded")

    collaborators, _api = _collaborators(document, events, validator=fail_validation)

    result = run_body_create(collaborators, "Doc", "Body")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_HEALTH_DEGRADED"
    assert document.objects == {}
    assert events == ["apply", "recompute", "inspect", "validate", "abort"]


def test_native_rejection_never_returns_cached_success():
    events = []
    document = _Document(events)
    collaborators, _api = _collaborators(
        document,
        events,
        final_result={"status": "PublicationFailed", "committed": False},
    )

    result = run_body_create(collaborators, "Doc", "Body")

    assert result["success"] is False
    assert result["error_code"] == "NATIVE_COMPATIBILITY_MUTATION_REJECTED"
    assert result["native_status"] == "PublicationFailed"
    assert document.objects == {}
    assert events == ["apply", "recompute", "inspect", "validate", "abort"]


def test_native_capability_is_required_before_body_apply():
    events = []
    document = _Document(events)
    bridge = CollaborationAPI(document_lookup=lambda _name: document)
    collaborators = SimpleNamespace(
        freecad=SimpleNamespace(getDocument=lambda _name: document),
        validate_document_invariants=lambda _document: events.append("validate"),
        commit_body_create_mutation=bridge.commit_body_create_mutation,
    )

    result = run_body_create(collaborators, "Doc", "Body")

    assert result["success"] is False
    assert result["native_status"] == "Unsupported"
    assert document.add_calls == 0
    assert document.objects == {}
    assert events == []


def test_native_rollback_failure_remains_distinguishable():
    events = []
    document = _Document(events)
    collaborators, _api = _collaborators(
        document,
        events,
        final_result={
            "status": "RollbackFailed",
            "committed": False,
            "rollback_succeeded": False,
        },
    )

    result = run_body_create(collaborators, "Doc", "Body")

    assert result["success"] is False
    assert result["native_status"] == "RollbackFailed"
    assert result["rollback_succeeded"] is False


@pytest.mark.parametrize(
    ("document_type", "error_code"),
    [
        (_MissingAfterRecomputeDocument, "CREATED_OBJECT_MISSING"),
        (_ReplacingAfterRecomputeDocument, "CREATED_OBJECT_REPLACED"),
        (_WrongTypeAfterRecomputeDocument, "CREATED_OBJECT_WRONG_TYPE"),
    ],
)
def test_inspection_rejects_missing_replaced_or_wrong_type_body(
    document_type,
    error_code,
):
    events = []
    document = document_type(events)
    collaborators, _api = _collaborators(document, events)

    result = run_body_create(collaborators, "Doc", "Body")

    assert result["success"] is False
    assert result["error_code"] == error_code
    assert document.objects == {}
    assert "commit" not in events


def test_apply_and_inspect_use_the_native_admitted_document():
    events = []
    admitted = _NativeBridgeDocument(events)
    other = _NativeBridgeDocument([])
    other.objects["Body"] = _body("Body", label="Wrong document")
    lookups = []

    def changing_lookup(name):
        lookups.append(name)
        return admitted if len(lookups) == 1 else other

    bridge = CollaborationAPI(document_lookup=changing_lookup)
    collaborators = SimpleNamespace(
        validate_document_invariants=lambda _document: events.append("validate"),
        commit_body_create_mutation=bridge.commit_body_create_mutation,
    )

    result = run_body_create(collaborators, "Doc", "Body")

    assert result["success"] is True
    assert result["label"] == "Label for Body"
    assert lookups == ["Doc"]
    assert events == ["apply", "recompute", "inspect", "validate", "commit"]
    assert admitted.getObject("Body") is not None
    assert other.getObject("Body").Label == "Wrong document"


def test_response_uses_the_actual_name_assigned_by_freecad():
    events = []
    document = _Document(events, assigned_name="Body001")
    collaborators, _api = _collaborators(document, events)

    result = run_body_create(collaborators, "Doc", "RequestedBody")

    assert result["success"] is True
    assert result["body"] == "Body001"
    assert document.getObject("RequestedBody") is None
    assert document.getObject("Body001") is not None


def test_body_create_has_no_uncoordinated_source_entry_point():
    assert not hasattr(subject, "body_create_gui")
    template = (
        Path(__file__).parents[2]
        / "src"
        / "freecad_mcp"
        / "templates"
        / "parametric"
        / "body_create.py.txt"
    )
    assert not template.exists()


@pytest.mark.parametrize(
    "native_result",
    [
        None,
        {},
        {"status": "FutureStatus", "committed": False},
        {"status": "Committed", "committed": False},
        {"status": "Busy", "committed": True},
        {"status": "Committed", "committed": 1},
        {"status": "Committed", "committed": True, "rollback_failed": True},
        {"status": "Committed", "committed": True, "rollback_succeeded": True},
        {"status": "Committed", "committed": True, "rollback_failed": "false"},
    ],
)
def test_unknown_or_contradictory_native_evidence_cannot_release_success(native_result):
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.body_mutation import (
        _body_native_result,
        _NativeBodyMutationState,
    )

    result = _body_native_result(native_result, _NativeBodyMutationState(postcondition_passed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["retry_safe"] is False


def test_exception_after_native_apply_does_not_claim_rollback():
    events = []
    document = _Document(events)

    def native_exception(_name, apply, _postcondition):
        apply(document)
        raise RuntimeError("native result unavailable")

    collaborators = SimpleNamespace(
        commit_body_create_mutation=native_exception,
        validate_document_invariants=lambda _: None,
    )
    result = run_body_create(collaborators, "Doc", "Body")
    assert document.getObject("Body") is not None
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


__all__: list[str] = []
