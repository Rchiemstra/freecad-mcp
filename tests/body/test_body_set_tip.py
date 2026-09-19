"""Unit coverage for the typed ``body_set_tip`` mutation slice."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from addon.FreeCADMCP.collaboration_api import CollaborationAPI
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import body_set_tip as subject
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.body_set_tip import (
    run_body_set_tip,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.typed_rpc_discovery import (
    discover_typed_rpc_handlers,
)

pytestmark = pytest.mark.unit


def _feature(name: str, *, type_id: str = "PartDesign::Pad"):
    return SimpleNamespace(
        Name=name,
        Label=name,
        TypeId=type_id,
        isDerivedFrom=lambda type_name, _type_id=type_id: (
            _type_id == type_name
            or (
                type_name == "PartDesign::Feature"
                and _type_id.startswith("PartDesign::")
                and _type_id != "PartDesign::Body"
            )
            or (_type_id == "PartDesign::Body" and type_name == "PartDesign::Body")
        ),
    )


class _Body:
    def __init__(self, name: str, tip, events: list[str] | None = None, *, label: str | None = None, group=None):
        self.Name = name
        self.Label = label if label is not None else f"Label for {name}"
        self.TypeId = "PartDesign::Body"
        self._tip = tip
        self._events = events
        self.Group = list(group) if group is not None else ([tip] if tip is not None else [])

    def isDerivedFrom(self, type_name: str) -> bool:
        return type_name == "PartDesign::Body"

    @property
    def Tip(self):
        return self._tip

    @Tip.setter
    def Tip(self, value) -> None:
        if self._events is not None:
            self._events.append("apply")
        self._tip = value


class _MutateThenRaiseBody(_Body):
    @property
    def Tip(self):
        return self._tip

    @Tip.setter
    def Tip(self, value) -> None:
        if self._events is not None:
            self._events.append("apply")
        self._tip = value
        raise RuntimeError("FreeCAD failed after assigning the Tip")


def _snapshot_tips(objects: dict[str, Any]) -> dict[str, Any]:
    return {name: getattr(obj, "_tip", getattr(obj, "Tip", None)) for name, obj in objects.items()}


def _restore_tips(objects: dict[str, Any], tips: dict[str, Any]) -> None:
    for name, tip in tips.items():
        obj = objects.get(name)
        if obj is not None and hasattr(obj, "_tip"):
            obj._tip = tip


class _Document:
    Name = "Doc"

    def __init__(self, events: list[str]) -> None:
        self.events = events
        pad = _feature("Pad", type_id="PartDesign::Pad")
        pocket = _feature("Pocket", type_id="PartDesign::Pocket")
        other_pad = _feature("OtherPad", type_id="PartDesign::Pad")
        self.objects: dict[str, Any] = {
            "Pad": pad,
            "Pocket": pocket,
            "OtherPad": other_pad,
            "Body": _Body("Body", pad, events, group=[pad, pocket]),
            "OtherBody": _Body("OtherBody", other_pad, events, group=[other_pad]),
            "Sketch": _feature("Sketch", type_id="Sketcher::SketchObject"),
        }
        self.recomputed = False

    def getObject(self, name):
        item = self.objects.get(name)
        if item is not None and self.recomputed and name == "Body":
            self.events.append("inspect")
        return item

    def recompute(self):
        self.events.append("recompute")
        self.recomputed = True


class _MissingAfterRecomputeDocument(_Document):
    def recompute(self):
        super().recompute()
        self.objects.pop("Body", None)


class _ReplacingAfterRecomputeDocument(_Document):
    def recompute(self):
        super().recompute()
        self.objects["Body"] = _Body("Body", self.objects["Pocket"], self.events, label="Replacement")


class _WrongTypeAfterRecomputeDocument(_Document):
    def recompute(self):
        super().recompute()
        self.objects["Body"].TypeId = "Part::Feature"
        self.objects["Body"].isDerivedFrom = lambda _type_name: False


class _TipNotUpdatedDocument(_Document):
    def recompute(self):
        super().recompute()
        self.objects["Body"]._tip = self.objects["Pad"]


class _MutateThenRaiseDocument(_Document):
    def __init__(self, events: list[str]) -> None:
        super().__init__(events)
        original = self.objects["Body"]
        self.objects["Body"] = _MutateThenRaiseBody(
            original.Name,
            original.Tip,
            events,
            label=original.Label,
            group=original.Group,
        )


class _RecomputeFailureDocument(_Document):
    def recompute(self):
        super().recompute()
        raise RuntimeError("FreeCAD recompute failed")


class _NativeBridgeDocument(_Document):
    """Document-shaped native binding used through the production bridge."""

    def commitCompatibilityMutation(self, callback, *, structural=False, postcondition=None, recompute=True):
        assert structural is True
        before_objects = dict(self.objects)
        before_tips = _snapshot_tips(self.objects)
        before_recomputed = self.recomputed
        try:
            callback()
            self.recompute()
            if postcondition is not None and not postcondition():
                self.objects = before_objects
                _restore_tips(self.objects, before_tips)
                self.recomputed = before_recomputed
                self.events.append("abort")
                return {"status": "PostconditionFailed", "committed": False}
        except Exception:
            self.objects = before_objects
            _restore_tips(self.objects, before_tips)
            self.recomputed = before_recomputed
            self.events.append("abort")
            return {"status": "ApplyFailed", "committed": False}
        self.events.append("commit")
        return {"status": "Committed", "committed": True}


class _CompatibilityAPI:
    """Stand-in modeling every native phase used by Body Tip assignment."""

    def __init__(self, document: _Document | None, *, final_result=None) -> None:
        self.document = document
        self.final_result = final_result
        self.calls = []

    def _restore(self, objects, tips, recomputed) -> None:
        assert self.document is not None
        self.document.objects = objects
        _restore_tips(self.document.objects, tips)
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
        before_tips = _snapshot_tips(self.document.objects)
        before_recomputed = self.document.recomputed
        try:
            callback(self.document) if bind_document else callback()
        except Exception as exc:
            self._restore(before_objects, before_tips, before_recomputed)
            return {"status": "ApplyFailed", "committed": False, "message": str(exc)}

        try:
            self.document.recompute()
        except Exception as exc:
            self._restore(before_objects, before_tips, before_recomputed)
            return {
                "status": "RecomputeFailed",
                "committed": False,
                "rollback_succeeded": True,
                "message": str(exc),
            }

        if postcondition is not None:
            satisfied = postcondition(self.document) if bind_document else postcondition()
            if not satisfied:
                self._restore(before_objects, before_tips, before_recomputed)
                return {
                    "status": "PostconditionFailed",
                    "committed": False,
                    "rollback_succeeded": True,
                }

        if self.final_result is not None:
            result = dict(self.final_result)
            if not result.get("committed"):
                self._restore(before_objects, before_tips, before_recomputed)
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


def _collaborators(
    document: _Document | None,
    events: list[str],
    *,
    validator=None,
    final_result=None,
):
    api = _CompatibilityAPI(document, final_result=final_result)
    collaborators = SimpleNamespace(
        validate_document_invariants=(
            validator if validator is not None else lambda _document: events.append("validate")
        ),
        commit_native_mutation=api.commit_native_mutation,
    )
    return collaborators, api


def test_body_set_tip_runs_apply_recompute_inspect_validate_then_commits():
    events = []
    document = _Document(events)
    collaborators, api = _collaborators(document, events)

    result = run_body_set_tip(collaborators, "Doc", "Body", "Pocket")

    assert result == {
        "contract_version": 1,
        "success": True,
        "ok": True,
        "outcome": "committed",
        "committed": True,
        "retry_safe": False,
        "body": "Body",
        "tip": "Pocket",
        "feature": "Pocket",
    }
    assert document.objects["Body"].Tip is document.objects["Pocket"]
    assert events == ["apply", "recompute", "inspect", "validate", "commit"]
    assert api.calls == [("Doc", True, True, True)]


def test_cad_methods_binds_discovered_body_set_tip_handler():
    from addon.FreeCADMCP.rpc_server.methods import cad_methods

    handlers = discover_typed_rpc_handlers()
    assert handlers["body_set_tip"] is subject.rpc_body_set_tip
    assert cad_methods.body_set_tip is handlers["body_set_tip"]


@pytest.mark.parametrize("feature_name", [None, 42, [], {}, "", " ", "\t\r\n"])
def test_invalid_names_abort_without_recompute_or_commit(feature_name):
    events = []
    document = _Document(events)
    original_tip = document.objects["Body"].Tip
    collaborators, _api = _collaborators(document, events)

    result = run_body_set_tip(collaborators, "Doc", "Body", feature_name)

    assert result["success"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"
    assert document.objects["Body"].Tip is original_tip
    assert "recompute" not in events
    assert "commit" not in events


def test_missing_document_fails_without_entering_the_apply_callback():
    events = []
    collaborators, api = _collaborators(None, events)

    result = run_body_set_tip(collaborators, "Missing", "Body", "Pocket")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
    assert api.calls == [("Missing", True, True, True)]
    assert events == []


def test_missing_body_aborts_without_recompute_or_commit():
    events = []
    document = _Document(events)
    document.objects.pop("Body")
    collaborators, _api = _collaborators(document, events)

    result = run_body_set_tip(collaborators, "Doc", "Body", "Pocket")

    assert result["success"] is False
    assert result["error_code"] == "BODY_NOT_FOUND"
    assert "recompute" not in events
    assert "commit" not in events


def test_missing_feature_aborts_without_recompute_or_commit():
    events = []
    document = _Document(events)
    original_tip = document.objects["Body"].Tip
    collaborators, _api = _collaborators(document, events)

    result = run_body_set_tip(collaborators, "Doc", "Body", "MissingFeature")

    assert result["success"] is False
    assert result["error_code"] == "FEATURE_NOT_FOUND"
    assert document.objects["Body"].Tip is original_tip
    assert "recompute" not in events
    assert "commit" not in events


def test_sketch_as_tip_is_rejected_as_wrong_type():
    events = []
    document = _Document(events)
    original_tip = document.objects["Body"].Tip
    collaborators, _api = _collaborators(document, events)

    result = run_body_set_tip(collaborators, "Doc", "Body", "Sketch")

    assert result["success"] is False
    assert result["error_code"] == "FEATURE_WRONG_TYPE"
    assert document.objects["Body"].Tip is original_tip
    assert "recompute" not in events
    assert "commit" not in events


def test_feature_from_other_body_is_rejected():
    events = []
    document = _Document(events)
    original_tip = document.objects["Body"].Tip
    collaborators, _api = _collaborators(document, events)

    result = run_body_set_tip(collaborators, "Doc", "Body", "OtherPad")

    assert result["success"] is False
    assert result["error_code"] == "FEATURE_NOT_IN_BODY"
    assert document.objects["Body"].Tip is original_tip
    assert "recompute" not in events
    assert "commit" not in events


def test_creation_that_changes_then_raises_is_rolled_back():
    events = []
    document = _MutateThenRaiseDocument(events)
    original_tip = document.objects["Body"].Tip
    collaborators, _api = _collaborators(document, events)

    result = run_body_set_tip(collaborators, "Doc", "Body", "Pocket")

    assert result["success"] is False
    assert result["error_code"] == "BODY_SET_TIP_FAILED"
    assert document.objects["Body"].Tip is original_tip
    assert events == ["apply", "abort"]


def test_recompute_failure_is_rolled_back():
    events = []
    document = _RecomputeFailureDocument(events)
    original_tip = document.objects["Body"].Tip
    collaborators, _api = _collaborators(document, events)

    result = run_body_set_tip(collaborators, "Doc", "Body", "Pocket")

    assert result["success"] is False
    assert result["error_code"] == "NATIVE_COMPATIBILITY_MUTATION_REJECTED"
    assert result["native_status"] == "RecomputeFailed"
    assert result["rollback_succeeded"] is True
    assert document.objects["Body"].Tip is original_tip
    assert events == ["apply", "recompute", "abort"]


def test_failed_validation_aborts_before_commit():
    events = []
    document = _Document(events)
    original_tip = document.objects["Body"].Tip

    def fail_validation(_document):
        events.append("validate")
        raise RuntimeError("document health degraded")

    collaborators, _api = _collaborators(document, events, validator=fail_validation)

    result = run_body_set_tip(collaborators, "Doc", "Body", "Pocket")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_HEALTH_DEGRADED"
    assert document.objects["Body"].Tip is original_tip
    assert events == ["apply", "recompute", "inspect", "validate", "abort"]


def test_native_rejection_never_returns_cached_success():
    events = []
    document = _Document(events)
    original_tip = document.objects["Body"].Tip
    collaborators, _api = _collaborators(
        document,
        events,
        final_result={"status": "PublicationFailed", "committed": False},
    )

    result = run_body_set_tip(collaborators, "Doc", "Body", "Pocket")

    assert result["success"] is False
    assert result["error_code"] == "NATIVE_COMPATIBILITY_MUTATION_REJECTED"
    assert result["native_status"] == "PublicationFailed"
    assert document.objects["Body"].Tip is original_tip
    assert events == ["apply", "recompute", "inspect", "validate", "abort"]


def test_native_capability_is_required_before_tip_apply():
    events = []
    document = _Document(events)
    original_tip = document.objects["Body"].Tip
    bridge = CollaborationAPI(document_lookup=lambda _name: document)
    collaborators = SimpleNamespace(
        validate_document_invariants=lambda _document: events.append("validate"),
        commit_native_mutation=bridge.commit_native_mutation,
    )

    result = run_body_set_tip(collaborators, "Doc", "Body", "Pocket")

    assert result["success"] is False
    assert result["native_status"] == "Unsupported"
    assert document.objects["Body"].Tip is original_tip
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

    result = run_body_set_tip(collaborators, "Doc", "Body", "Pocket")

    assert result["success"] is False
    assert result["native_status"] == "RollbackFailed"
    assert result["rollback_succeeded"] is False


@pytest.mark.parametrize(
    ("document_type", "error_code"),
    [
        (_MissingAfterRecomputeDocument, "BODY_NOT_FOUND"),
        (_ReplacingAfterRecomputeDocument, "BODY_REPLACED"),
        (_WrongTypeAfterRecomputeDocument, "BODY_WRONG_TYPE"),
        (_TipNotUpdatedDocument, "TIP_NOT_UPDATED"),
    ],
)
def test_inspection_rejects_missing_replaced_wrong_type_or_stale_tip(
    document_type,
    error_code,
):
    events = []
    document = document_type(events)
    original_tip = document.objects["Body"].Tip if "Body" in document.objects else None
    collaborators, _api = _collaborators(document, events)

    result = run_body_set_tip(collaborators, "Doc", "Body", "Pocket")

    assert result["success"] is False
    assert result["error_code"] == error_code
    if original_tip is not None and "Body" in document.objects:
        assert document.objects["Body"].Tip is original_tip
    assert "commit" not in events


def test_apply_and_inspect_use_the_native_admitted_document():
    events = []
    admitted = _NativeBridgeDocument(events)
    other = _NativeBridgeDocument([])
    lookups = []

    def changing_lookup(name):
        lookups.append(name)
        return admitted if len(lookups) == 1 else other

    bridge = CollaborationAPI(document_lookup=changing_lookup)
    collaborators = SimpleNamespace(
        validate_document_invariants=lambda _document: events.append("validate"),
        commit_native_mutation=bridge.commit_native_mutation,
    )

    result = run_body_set_tip(collaborators, "Doc", "Body", "Pocket")

    assert result["success"] is True
    assert result["tip"] == "Pocket"
    assert lookups == ["Doc"]
    assert events == ["apply", "recompute", "inspect", "validate", "commit"]
    assert admitted.getObject("Body").Tip is admitted.getObject("Pocket")
    assert other.getObject("Body").Tip is other.getObject("Pad")


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
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.body_set_tip_mutation import (
        _NativeTipMutationState,
        _body_set_tip_native_result,
    )

    result = _body_set_tip_native_result(native_result, _NativeTipMutationState(postcondition_passed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["retry_safe"] is False


def test_exception_after_native_apply_does_not_claim_rollback():
    events = []
    document = _Document(events)

    def native_exception(_name, apply, _postcondition, *, structural=True):
        apply(document)
        raise RuntimeError("native result unavailable")

    collaborators = SimpleNamespace(
        commit_native_mutation=native_exception,
        validate_document_invariants=lambda _: None,
    )
    result = run_body_set_tip(collaborators, "Doc", "Body", "Pocket")
    assert document.objects["Body"].Tip is document.objects["Pocket"]
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_typed_path_has_no_gui_leaf_entry_point():
    assert not hasattr(subject, "body_set_tip_gui")


__all__: list[str] = []
