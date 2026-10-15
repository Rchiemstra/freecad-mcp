"""Cross-document recompute fallback must require confirmed rollback."""
from types import SimpleNamespace
import pytest
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import clear_expression as subject
from addon.FreeCADMCP._shared.protocol.clear_expression_contract import make_clear_expression_failure, make_clear_expression_uncertain
from tests.clear.test_clear_expression import _Document, _item

pytestmark = pytest.mark.unit


def _run(monkeypatch, first_failure=None, direct_failure=False):
    events = []
    doc = _Document(events)
    item = _item("Pad")
    item.setExpression("Length", "Source#Dims.PadH")
    doc.objects["Pad"] = item
    calls = []
    def native(_collaborators, _name, apply, inspect, **kwargs):
        calls.append(kwargs.get("recompute", True))
        if len(calls) == 1 and first_failure is not None:
            return first_failure
        apply(doc)
        inspect(doc)
        return True
    monkeypatch.setattr(subject, "run_clear_expression_native_mutation", native)
    if direct_failure:
        def failed():
            raise RuntimeError("direct recompute failed")
        doc.recompute = failed
    collab = SimpleNamespace(validate_document_invariants=lambda _d: events.append("validate"))
    result = subject.run_clear_expression(collab, "Doc", "Pad", "Length")
    return result, calls, events, item


def test_clear_normal_native_commit_does_not_recompute_twice(monkeypatch):
    result, calls, events, item = _run(monkeypatch)
    assert result["committed"] is True
    assert calls == [True]
    assert "recompute" not in events
    assert item.getExpression("Length") is None


def _dependency_failure():
    return make_clear_expression_failure("NATIVE_COMPATIBILITY_MUTATION_REJECTED",
        "generic recompute has an unresolved cross-document dependency",
        native_status="RecomputeFailed", rollback_succeeded=True, rollback_failed=False)


def test_clear_cross_document_retries_only_after_confirmed_dependency_rollback(monkeypatch):
    result, calls, events, item = _run(monkeypatch, _dependency_failure())
    assert result["success"] is True
    assert calls == [True, False]
    assert events == ["recompute", "validate", "inspect"]
    assert item.getExpression("Length") is None


@pytest.mark.parametrize("failure", [
    make_clear_expression_failure("OTHER", "unrelated failure", rollback_succeeded=True),
    make_clear_expression_uncertain("UNKNOWN", "generic recompute has an unresolved cross-document dependency", committed=None),
])
def test_clear_never_retries_unrelated_or_uncertain_failure(monkeypatch, failure):
    result, calls, _, item = _run(monkeypatch, failure)
    assert result == failure
    assert calls == [True]
    assert item.getExpression("Length") == "Source#Dims.PadH"


def test_direct_recompute_failure_reports_committed_clear_as_uncertain(monkeypatch):
    result, calls, _, item = _run(monkeypatch, _dependency_failure(), direct_failure=True)
    assert result["outcome"] == "uncertain"
    assert result["committed"] is True
    assert result["error_code"] == "EXPRESSION_RECOMPUTE_FAILED"
    assert item.getExpression("Length") is None


def _constraint_repair(monkeypatch, failure=None):
    from addon.FreeCADMCP.rpc_server.mutation_guard_ops.validate_invariants import validate_document_invariants

    events = []
    doc = _Document(events)
    detail = "Document 'SrcDoc' not found in 'SrcDoc'\nin property binding 'Doc#Sketch.Constraints'"
    item = _item("Sketch", type_id="Sketcher::SketchObject")
    item.PropertiesList = ["Constraints"]
    item.State = ["Invalid"]
    item.error = detail
    item.getStatusString = lambda: item.error
    item.ExpressionEngine = [(".Constraints.W", "SrcDoc#<<Dims>>.Wall"),
                             (".Constraints.H", "SrcDoc#<<Dims>>.PadLen")]
    def clear(path):
        item.ExpressionEngine = [(p, e) for p, e in item.ExpressionEngine if p.lstrip(".") != path]
        item.State = ["Invalid", "Touched"]
    item.clearExpression = clear
    doc.objects["Sketch"] = item
    if failure == "blocked":
        downstream = _item("Pad", type_id="PartDesign::Pad")
        downstream.OutList = [item]
        downstream.getStatusString = lambda: "dependency did not commit: Sketch"
        doc.objects["Pad"] = downstream
    def recompute():
        item.State = ["Invalid"]
        if failure == "blocked":
            downstream.State = ["Invalid"]
        if failure == "changed_error":
            item.error = "a different solver failure"
        elif failure == "new_error":
            other = _item("Other", type_id="Part::Feature")
            other.State = ["Invalid"]
            other.getStatusString = lambda: "new failure"
            doc.objects["Other"] = other
        elif failure == "retained_binding":
            item.ExpressionEngine.append((".Constraints.New", "99 mm"))
    doc.recompute = recompute
    calls = []
    def native(_collaborators, _name, apply, inspect, **kwargs):
        calls.append(kwargs.get("recompute", True))
        apply(doc)
        if len(calls) == 1:
            # The native coordinator restored the pre-apply expression list.
            item.ExpressionEngine = [(".Constraints.W", "SrcDoc#<<Dims>>.Wall"),
                                     (".Constraints.H", "SrcDoc#<<Dims>>.PadLen")]
            item.State = ["Invalid"]
            return make_clear_expression_failure("NATIVE_COMPATIBILITY_MUTATION_REJECTED",
                "document recompute reported an object error: Sketch (" + detail + ")",
                native_status="RecomputeFailed", rollback_succeeded=True, rollback_failed=False)
        inspect(doc)
        _collaborators.validate_document_invariants(doc)
        return True
    monkeypatch.setattr(subject, "run_clear_expression_native_mutation", native)
    result = subject.run_clear_expression(SimpleNamespace(validate_document_invariants=validate_document_invariants),
                                          "Doc", "Sketch", "Constraints.W")
    return result, calls, item


def test_clear_constraint_retaining_missing_source_can_commit_after_confirmed_rollback(monkeypatch):
    result, calls, item = _constraint_repair(monkeypatch)
    assert result["success"] is True, result
    assert calls == [True, False]
    assert item.ExpressionEngine == [(".Constraints.H", "SrcDoc#<<Dims>>.PadLen")]


@pytest.mark.parametrize("failure", ["changed_error", "new_error", "retained_binding"])
def test_constraint_repair_reports_new_post_commit_failures(monkeypatch, failure):
    result, calls, _ = _constraint_repair(monkeypatch, failure)
    assert calls == [True, False]
    assert result["outcome"] == "uncertain", result
    assert result["committed"] is True
    assert result["retry_safe"] is False


def test_constraint_repair_retains_only_explained_native_downstream_errors(monkeypatch):
    result, calls, _ = _constraint_repair(monkeypatch, "blocked")
    assert result["success"] is True, result
    assert calls == [True, False]
