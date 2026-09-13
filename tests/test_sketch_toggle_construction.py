"""Unit coverage for the typed ``sketch_toggle_construction`` mutation slice."""

from __future__ import annotations

from pathlib import Path

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import sketch_toggle_construction as subject
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_toggle_construction import run_sketch_toggle_construction
from tests.sketch_exec_support import (
    FakeDocument,
    MissingAfterRecomputeDocument,
    MutateThenRaiseDocument,
    NativeBridgeDocument,
    RecomputeFailureDocument,
    ReplacingAfterRecomputeDocument,
    WrongTypeAfterRecomputeDocument,
    collaborators,
    native_bridge_collaborators,
)

pytestmark = pytest.mark.unit


def _prepare(document, events):
    sketch = document.sketch
    previous = (sketch.fail_after_add, sketch.fail_after_constraint, sketch.fail_after_edit)
    sketch.fail_after_add = False
    sketch.fail_after_constraint = False
    sketch.fail_after_edit = False
    document.sketch.addGeometry(object(), False)
    document.sketch.addGeometry(object(), False)
    sketch.fail_after_add, sketch.fail_after_constraint, sketch.fail_after_edit = previous
    events.clear()


def test_sketch_toggle_construction_runs_apply_recompute_inspect_validate_then_commits():
    events = []
    document = FakeDocument(events)
    _prepare(document, events)
    collab, api = collaborators(document, events)

    result = run_sketch_toggle_construction(collab, "Doc", "Sketch", [0], True)

    assert result["success"] is True
    assert result["committed"] is True
    assert result["retry_safe"] is False
    assert result["sketch"] == "Sketch"
    assert events == ["apply", "recompute", "inspect", "validate", "commit"]
    assert api.calls == [("Doc", True, True, True)]


@pytest.mark.parametrize("sketch_name", [None, 42, [], {}, "", " ", "\t"])
def test_invalid_names_abort_without_recompute_or_commit(sketch_name):
    events = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)

    result = run_sketch_toggle_construction(collab, "Doc", sketch_name, [0], True)

    assert result["success"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"
    assert "recompute" not in events
    assert "commit" not in events


def test_missing_document_fails_without_entering_the_apply_callback():
    events = []
    collab, api = collaborators(None, events)

    result = run_sketch_toggle_construction(collab, "Missing", "Sketch", [0], True)

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
    assert api.calls == [("Missing", True, True, True)]
    assert events == []


def test_missing_sketch_is_rolled_back_or_rejected():
    events = []
    document = FakeDocument(events)
    document.objects.clear()
    collab, _api = collaborators(document, events)

    result = run_sketch_toggle_construction(collab, "Doc", "Sketch", [0], True)

    assert result["success"] is False
    assert result["error_code"] == "SKETCH_NOT_FOUND"


def test_creation_that_changes_then_raises_is_rolled_back():
    events = []
    document = MutateThenRaiseDocument(events)
    _prepare(document, events)
    collab, _api = collaborators(document, events)

    result = run_sketch_toggle_construction(collab, "Doc", "Sketch", [0], True)

    assert result["success"] is False
    assert result["committed"] is False
    assert "abort" in events


def test_recompute_failure_is_rolled_back():
    events = []
    document = RecomputeFailureDocument(events)
    _prepare(document, events)
    collab, _api = collaborators(document, events)

    result = run_sketch_toggle_construction(collab, "Doc", "Sketch", [0], True)

    assert result["success"] is False
    assert result["error_code"] == "NATIVE_COMPATIBILITY_MUTATION_REJECTED"
    assert result["native_status"] == "RecomputeFailed"
    assert result["rollback_succeeded"] is True
    assert "abort" in events


def test_failed_validation_aborts_before_commit():
    events = []
    document = FakeDocument(events)
    _prepare(document, events)

    def fail_validation(_document):
        events.append("validate")
        raise RuntimeError("document health degraded")

    collab, _api = collaborators(document, events, validator=fail_validation)

    result = run_sketch_toggle_construction(collab, "Doc", "Sketch", [0], True)

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_HEALTH_DEGRADED"
    assert "commit" not in events


def test_native_rejection_never_returns_cached_success():
    events = []
    document = FakeDocument(events)
    _prepare(document, events)
    collab, _api = collaborators(
        document,
        events,
        final_result={"status": "PublicationFailed", "committed": False},
    )

    result = run_sketch_toggle_construction(collab, "Doc", "Sketch", [0], True)

    assert result["success"] is False
    assert result["error_code"] == "NATIVE_COMPATIBILITY_MUTATION_REJECTED"
    assert result["native_status"] == "PublicationFailed"


def test_native_capability_is_required_before_apply():
    events = []
    document = FakeDocument(events)
    _prepare(document, events)
    collab = native_bridge_collaborators(document, events)

    result = run_sketch_toggle_construction(collab, "Doc", "Sketch", [0], True)

    assert result["success"] is False
    assert result["native_status"] == "Unsupported"
    assert events == []


def test_native_rollback_failure_remains_distinguishable():
    events = []
    document = FakeDocument(events)
    _prepare(document, events)
    collab, _api = collaborators(
        document,
        events,
        final_result={
            "status": "RollbackFailed",
            "committed": False,
            "rollback_succeeded": False,
        },
    )

    result = run_sketch_toggle_construction(collab, "Doc", "Sketch", [0], True)

    assert result["success"] is False
    assert result["native_status"] == "RollbackFailed"
    assert result["rollback_succeeded"] is False


@pytest.mark.parametrize(
    ("document_type", "error_code"),
    [
        (MissingAfterRecomputeDocument, "SKETCH_MISSING"),
        (ReplacingAfterRecomputeDocument, "SKETCH_REPLACED"),
        (WrongTypeAfterRecomputeDocument, "SKETCH_WRONG_TYPE"),
    ],
)
def test_inspection_rejects_missing_replaced_or_wrong_type_sketch(document_type, error_code):
    events = []
    document = document_type(events)
    _prepare(document, events)
    collab, _api = collaborators(document, events)

    result = run_sketch_toggle_construction(collab, "Doc", "Sketch", [0], True)

    assert result["success"] is False
    assert result["error_code"] == error_code
    assert "commit" not in events


def test_apply_and_inspect_use_the_native_admitted_document():
    events = []
    admitted = NativeBridgeDocument(events)
    _prepare(admitted, events)
    other = NativeBridgeDocument([])
    lookups = []

    def changing_lookup(name):
        lookups.append(name)
        return admitted if len(lookups) == 1 else other

    collab = native_bridge_collaborators(admitted, events, lookup=changing_lookup)

    result = run_sketch_toggle_construction(collab, "Doc", "Sketch", [0], True)

    assert result["success"] is True
    assert lookups == ["Doc"]
    assert "commit" in events


def test_sketch_toggle_construction_has_no_uncoordinated_source_entry_point():
    assert not hasattr(subject, "sketch_toggle_construction_gui")
    template = Path(__file__).parents[1] / 'src/freecad_mcp/templates/p1_curves/sketch_toggle_construction.py.txt'
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
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_toggle_construction_mutation import (
        _sketch_toggle_construction_native_result,
        _NativeSketchToggleConstructionMutationState,
    )

    result = _sketch_toggle_construction_native_result(
        native_result, _NativeSketchToggleConstructionMutationState(postcondition_passed=True)
    )
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["retry_safe"] is False


def test_exception_after_native_apply_does_not_claim_rollback():
    events = []
    document = FakeDocument(events)
    _prepare(document, events)

    def native_exception(_name, apply, _postcondition, *, structural=True):
        apply(document)
        raise RuntimeError("native result unavailable")

    from types import SimpleNamespace
    from tests.sketch_exec_support import FakeFreeCAD, FakePart, FakeSketcher

    collab = SimpleNamespace(
        freecad=FakeFreeCAD(),
        part=FakePart(),
        sketcher=FakeSketcher(),
        commit_native_mutation=native_exception,
        validate_document_invariants=lambda _: None,
    )
    result = run_sketch_toggle_construction(collab, "Doc", "Sketch", [0], True)
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False
