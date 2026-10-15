"""Native repairs retain existing model errors without weakening postflight."""
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.collaboration_api import CollaborationAPI
from addon.FreeCADMCP.rpc_method_context import current_rpc_method, rpc_method_scope
from addon.FreeCADMCP.rpc_server.mutation_guard_ops.validate_invariants import validate_document_invariants

pytestmark = pytest.mark.unit


def _object(name="Bridge", error="Document 'SrcDoc' not found"):
    obj = SimpleNamespace(Name=name, TypeId="Spreadsheet::Sheet", State=["Invalid"] if error else [],
                          error=error, isDerivedFrom=lambda _type: False)
    obj.getStatusString = lambda: obj.error or "Valid"
    return obj


class _Document:
    Name = "DepDoc"

    def __init__(self, objects):
        self.Objects = objects

    def commitCompatibilityMutation(self, callback, *, structural=False, postcondition=None, recompute=True):
        callback()
        if postcondition and not postcondition():
            return {"status": "PostconditionFailed", "committed": False}
        return {"status": "Committed", "committed": True}


def _commit(document, callback=lambda _doc: None):
    with rpc_method_scope(current_rpc_method() or "clear_expression"):
        return CollaborationAPI(document_lookup=lambda _name: document).commit_native_mutation(
            "DepDoc", callback, lambda doc: validate_document_invariants(doc),
        )


@pytest.mark.parametrize("existing_error", [False, True], ids=["happy_clean", "defect_native_error"])
def test_native_repair_preserves_existing_error(existing_error):
    document = _Document([_object(error="Document 'SrcDoc' not found" if existing_error else "")])
    result = _commit(document)
    assert result["committed"] is True, result
    if existing_error:
        # The exception is admitted only inside this native postcondition.
        with pytest.raises(RuntimeError, match="SrcDoc"):
            validate_document_invariants(document)


@pytest.mark.parametrize("change", ["new_error", "changed_error", "replacement", "proxy", "body_tip", "invalid"])
def test_native_repair_rejects_health_degradation(change):
    original = _object()
    document = _Document([original])

    def mutate(doc):
        if change == "new_error":
            doc.Objects.append(_object("Other", "new error"))
        elif change == "changed_error":
            original.error = "different error"
        elif change == "replacement":
            doc.Objects[:] = [_object()]
        elif change == "proxy":
            original.Proxy = object()
        elif change == "invalid":
            original.State.append("Error")
        else:
            doc.Objects.append(SimpleNamespace(Name="Body", State=[], TypeId="PartDesign::Body",
                                               Group=(), Tip=object(), isDerivedFrom=lambda _type: True))

    result = _commit(document, mutate)
    assert result["status"] == "PostconditionFailed", result
    assert result["committed"] is False, result


@pytest.mark.parametrize("method", ["recompute_document", "recompute_and_wait", "measure_volume"])
def test_explicit_recompute_still_reports_existing_error(method):
    document = _Document([_object()])
    with rpc_method_scope(method):
        result = _commit(document)
    assert result["status"] == "PostconditionFailed", result
    assert result["committed"] is False, result


@pytest.mark.parametrize("pending", ["Touched", "Dirty", "cells"])
def test_native_repair_rejects_unsettled_existing_error(pending):
    original = _object()
    document = _Document([original])

    def mutate(_doc):
        if pending == "cells":
            original.getDirtyCells = lambda: ["B1"]
        else:
            original.State.append(pending)

    result = _commit(document, mutate)
    assert result["status"] == "PostconditionFailed", result
    assert result["committed"] is False, result


@pytest.mark.parametrize("expanded", [False, True], ids=["happy_unchanged", "defect_tree_expanded"])
def test_native_repair_ignores_tree_presentation_state(expanded):
    original = _object()
    document = _Document([original])
    def mutate(_doc):
        if expanded:
            original.State.append("Expanded")
    result = _commit(document, mutate)
    assert result["committed"] is True, result


@pytest.mark.parametrize("status,detail,accepted", [
    ("RecomputeFailed", "Document 'SrcDoc' not found in 'SrcDoc'", True),
    ("RollbackFailed", "Document 'SrcDoc' not found in 'SrcDoc'", False),
    ("RecomputeFailed", "new solver failure", False),
])
def test_missing_source_typed_edit_retries_only_proven_native_failure(status, detail, accepted):
    original = _object(error="Document 'SrcDoc' not found in 'SrcDoc'")
    original.ExpressionEngine = [("Length", "SrcDoc#Dims.Len")]
    original.value = 1
    original.purgeTouched = lambda: original.State.remove("Touched") if "Touched" in original.State else None
    class Document(_Document):
        commits = 0
        attempts = 0
        def recompute(self):
            original.State = ["Invalid", "Touched"]
        def commitCompatibilityMutation(self, callback, *, structural=False, postcondition=None, recompute=True):
            self.attempts += 1
            previous = original.value
            callback()
            if recompute:
                original.value = previous
                return {"status": status, "committed": False,
                        "message": "document recompute reported an object error: Bridge (" + detail + ")"}
            assert postcondition()
            self.commits += 1
            return {"status": "Committed", "committed": True}
    document = Document([original])
    with rpc_method_scope("sketch_edit_constraint"):
        result = _commit(document, lambda _doc: setattr(original, "value", 35))
    assert result["committed"] is accepted, result
    assert document.commits == int(accepted)
    assert original.value == (35 if accepted else 1)
    assert document.attempts == (2 if accepted else 1)


def test_missing_source_repair_cannot_admit_new_bindings_or_new_failed_objects():
    from addon.FreeCADMCP.native_error_boundary import (
        MissingSourceRepair, capture_native_error_baseline,
    )
    original = _object(error="Document 'SrcDoc' not found in 'SrcDoc'")
    original.ExpressionEngine = [("Length", "SrcDoc#Dims.Len")]
    document = _Document([original])
    repair = MissingSourceRepair(document, capture_native_error_baseline(document))
    original.ExpressionEngine.append(("Width", "SrcDoc#Dims.Width"))
    assert not repair.bindings_preserved()
    original.ExpressionEngine.pop()
    assert repair.bindings_preserved()
    extra = _object("New", "dependency did not commit: Bridge")
    extra.OutList = [original]
    document.Objects.append(extra)
    document.recompute = lambda: None
    with pytest.raises(RuntimeError, match="New"):
        repair.settle(validate_document_invariants)


def test_missing_source_repair_rejects_overwriting_a_surviving_bound_value():
    from addon.FreeCADMCP.native_error_boundary import MissingSourceRepair, capture_native_error_baseline
    original = _object(error="Document 'SrcDoc' not found in 'SrcDoc'")
    original.ExpressionEngine = [("Length", "SrcDoc#Dims.Len")]
    original.value = 15
    original.evalExpression = lambda _path: original.value
    document = _Document([original])
    repair = MissingSourceRepair(document, capture_native_error_baseline(document))
    assert repair.bindings_preserved()
    original.value = 12
    assert not repair.bindings_preserved()
    original.ExpressionEngine = []
    assert repair.bindings_preserved()
