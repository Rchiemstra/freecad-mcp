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
