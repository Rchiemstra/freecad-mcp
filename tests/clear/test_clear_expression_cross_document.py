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
