"""Unit coverage for the typed ``helical_sweep_feature`` mutation slice."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.collaboration_api import CollaborationAPI
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import helical_sweep_feature as subject
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.helical_sweep_feature import run_helical_sweep_feature
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.helical_sweep_feature_mutation import (
    _HelicalSweepFeatureNativeMutationState,
    _helical_sweep_feature_native_result,
)
from tests.typed_feature_fakes import (
    FeatureDocument,
    MissingAfterRecomputeDocument,
    MutateThenRaiseDocument,
    NativeBridgeDocument,
    RecomputeFailureDocument,
    ReplacingAfterRecomputeDocument,
    WrongTypeAfterRecomputeDocument,
    collaborators,
    prepare_document,
    production_bridge_collaborators,
)

pytestmark = pytest.mark.unit

_KWARGS = {'doc_name': 'Doc', 'profile_sketch': 'Sketch', 'helix_name': 'Helix', 'pitch': 2.0, 'height': 10.0, 'radius': 5.0, 'body_name': None, 'left_handed': False, 'reversed_dir': False}
_CREATED = 'helix_name'


def _run(collab, **overrides):
    payload = dict(_KWARGS)
    payload.update(overrides)
    return run_helical_sweep_feature(collab, **payload)


def test_helical_sweep_feature_runs_apply_recompute_inspect_validate_then_commits():
    events: list[str] = []
    document = FeatureDocument(events)
    prepare_document('profile', document)
    collab, api = collaborators(document, events)

    result = _run(collab)

    assert result["success"] is True
    assert result["feature"] == _KWARGS[_CREATED]
    assert result["label"] == f"Label for {_KWARGS[_CREATED]}"
    helix = document.objects[_KWARGS[_CREATED]]
    assert helix.Radius == 5.0
    assert events == ["apply", "recompute", "inspect", "validate", "commit"]
    assert api.calls == [("Doc", True, True, True)]


@pytest.mark.parametrize("value", [None, 42, [], {}, "", " ", "\t\r\n"])
def test_invalid_names_abort_without_recompute_or_commit(value):
    events: list[str] = []
    document = FeatureDocument(events)
    prepare_document('profile', document)
    collab, _api = collaborators(document, events)

    result = _run(collab, **{_CREATED: value})

    assert result["success"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"
    assert "recompute" not in events
    assert "commit" not in events


def test_missing_document_fails_without_entering_the_apply_callback():
    events: list[str] = []
    collab, api = collaborators(None, events)

    result = _run(collab, doc_name="Missing")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
    assert api.calls == [("Missing", True, True, True)]
    assert events == []


def test_duplicate_name_aborts_without_recompute_or_commit():
    events: list[str] = []
    document = FeatureDocument(events)
    prepare_document('profile', document)
    existing = document.register_object("App::FeaturePython", _KWARGS[_CREATED], event=None)
    collab, _api = collaborators(document, events)

    result = _run(collab)

    assert result["success"] is False
    assert result["error_code"] == "OBJECT_ALREADY_EXISTS"
    assert document.objects[_KWARGS[_CREATED]] is existing
    assert "recompute" not in events
    assert "commit" not in events


def test_creation_that_changes_then_raises_is_rolled_back():
    events: list[str] = []
    document = MutateThenRaiseDocument(events)
    prepare_document('profile', document)
    collab, _api = collaborators(document, events)

    result = _run(collab)

    assert result["success"] is False
    assert result["error_code"] == "HELICAL_SWEEP_FEATURE_FAILED"
    assert _KWARGS[_CREATED] not in document.objects or document.add_calls == 0
    assert "abort" in events


def test_recompute_failure_is_rolled_back():
    events: list[str] = []
    document = RecomputeFailureDocument(events)
    prepare_document('profile', document)
    collab, _api = collaborators(document, events)

    result = _run(collab)

    assert result["success"] is False
    assert result["error_code"] == "NATIVE_COMPATIBILITY_MUTATION_REJECTED"
    assert result["native_status"] == "RecomputeFailed"
    assert result["rollback_succeeded"] is True
    assert events[-1] == "abort"


def test_failed_validation_aborts_before_commit():
    events: list[str] = []
    document = FeatureDocument(events)
    prepare_document('profile', document)

    def fail_validation(_document):
        events.append("validate")
        raise RuntimeError("document health degraded")

    collab, _api = collaborators(document, events, validator=fail_validation)
    result = _run(collab)

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_HEALTH_DEGRADED"
    assert "commit" not in events
    assert "abort" in events


def test_native_rejection_never_returns_cached_success():
    events: list[str] = []
    document = FeatureDocument(events)
    prepare_document('profile', document)
    collab, _api = collaborators(
        document,
        events,
        final_result={"status": "PublicationFailed", "committed": False},
    )

    result = _run(collab)

    assert result["success"] is False
    assert result["error_code"] == "NATIVE_COMPATIBILITY_MUTATION_REJECTED"
    assert result["native_status"] == "PublicationFailed"
    assert "abort" in events


def test_native_capability_is_required_before_apply():
    events: list[str] = []
    document = FeatureDocument(events)
    prepare_document('profile', document)
    collab = production_bridge_collaborators(document, events)

    result = _run(collab)

    assert result["success"] is False
    assert result["native_status"] == "Unsupported"
    assert document.add_calls == 0
    assert events == []


def test_native_rollback_failure_remains_distinguishable():
    events: list[str] = []
    document = FeatureDocument(events)
    prepare_document('profile', document)
    collab, _api = collaborators(
        document,
        events,
        final_result={
            "status": "RollbackFailed",
            "committed": False,
            "rollback_succeeded": False,
        },
    )

    result = _run(collab)

    assert result["success"] is False
    assert result["native_status"] == "RollbackFailed"
    assert result["rollback_succeeded"] is False


@pytest.mark.parametrize(
    ("document_type", "error_code"),
    [
        (MissingAfterRecomputeDocument, "CREATED_OBJECT_MISSING"),
        (lambda events: ReplacingAfterRecomputeDocument(events, _KWARGS[_CREATED]), "CREATED_OBJECT_REPLACED"),
        (lambda events: WrongTypeAfterRecomputeDocument(events, _KWARGS[_CREATED]), "CREATED_OBJECT_WRONG_TYPE"),
    ],
)
def test_inspection_rejects_missing_replaced_or_wrong_type(document_type, error_code):
    events: list[str] = []
    document = document_type(events)
    prepare_document('profile', document)
    collab, _api = collaborators(document, events)

    result = _run(collab)

    assert result["success"] is False
    assert result["error_code"] == error_code
    assert "commit" not in events


def test_apply_and_inspect_use_the_native_admitted_document():
    events: list[str] = []
    admitted = NativeBridgeDocument(events)
    prepare_document('profile', admitted)
    other = NativeBridgeDocument([])
    lookups: list[str] = []

    def changing_lookup(name):
        lookups.append(name)
        return admitted if len(lookups) == 1 else other

    bridge = CollaborationAPI(document_lookup=changing_lookup)
    collab = SimpleNamespace(
        validate_document_invariants=lambda _document: events.append("validate"),
        commit_native_mutation=bridge.commit_native_mutation,
    )

    result = _run(collab)

    assert result["success"] is True
    assert lookups == ["Doc"]
    assert "commit" in events
    assert admitted.getObject(_KWARGS[_CREATED]) is not None


def test_response_uses_the_actual_name_assigned_by_freecad():
    events: list[str] = []
    document = FeatureDocument(events, assigned_name="Feature001")
    prepare_document('profile', document)
    collab, _api = collaborators(document, events)

    result = _run(collab)

    assert result["success"] is True
    assert result["feature"] == "Feature001"
    assert document.getObject(_KWARGS[_CREATED]) is None
    assert document.getObject("Feature001") is not None


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
    result = _helical_sweep_feature_native_result(
        native_result, _HelicalSweepFeatureNativeMutationState(postcondition_passed=True)
    )
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["retry_safe"] is False


def test_exception_after_native_apply_does_not_claim_rollback():
    events: list[str] = []
    document = FeatureDocument(events)
    prepare_document('profile', document)

    def native_exception(_name, apply, _postcondition, *, structural=True):
        del structural
        apply(document)
        raise RuntimeError("native result unavailable")

    collab = SimpleNamespace(
        commit_native_mutation=native_exception,
        validate_document_invariants=lambda _: None,
    )
    result = _run(collab)
    assert document.getObject(_KWARGS[_CREATED]) is not None
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_typed_rpc_handler_is_registered():
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.typed_rpc_discovery import (
        discover_typed_rpc_handlers,
    )

    assert "helical_sweep_feature" in discover_typed_rpc_handlers()
    assert subject.TYPED_RPC_HANDLER[0] == "helical_sweep_feature"
