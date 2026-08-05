"""Phase 15 contracts for eager CAD collaborator composition."""

from __future__ import annotations

import inspect
from dataclasses import fields, replace

import pytest

from addon.FreeCADMCP.rpc_server import rpc_server
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_mutation import (
    run_cad_mutation,
)
from addon.FreeCADMCP.rpc_server.mutation_guard_ops.method_spec_constants import (
    NATIVE_COMPATIBILITY_METHODS,
    NO_OUTER_TRANSACTION,
)

pytestmark = pytest.mark.unit


def _cad_collaborators(api) -> CadCollaborators:
    values = {
        name: (object() if name in {"freecad", "part", "sketcher"} else lambda *a, **k: None)
        for name in (field.name for field in fields(CadCollaborators))
        if name != "compatibility_api"
    }
    return CadCollaborators(compatibility_api=api, **values)


class _NativeAPI:
    def __init__(self, *, result=None, invoke=True):
        self.result = result or {"status": "Committed", "committed": True}
        self.invoke = invoke
        self.calls = []
        self.completed_callbacks = 0

    def commit_compatibility_mutation(
        self, document_name, callback, *, structural=False
    ):
        self.calls.append((document_name, callback, structural))
        if self.invoke:
            callback()
            self.completed_callbacks += 1
        return self.result


def test_cad_dependency_shape_is_explicit_and_policy_free() -> None:
    assert [field.name for field in fields(CadCollaborators)] == [
        "compatibility_api",
        "freecad",
        "part",
        "sketcher",
        "create_object_gui",
        "insert_part_from_library",
        "set_object_property",
        "serialize_object",
        "inspect_references_gui",
        "repair_references_gui",
        "recompute_and_wait",
        "run_fem_analysis",
        "dict_to_placement",
        "placement_to_dict",
        "set_extrusion_symmetric",
        "set_feature_bool",
        "validate_document_invariants",
    ]
    assert not {
        "lease_owner",
        "token",
        "generation",
        "heartbeat",
        "dirty_state",
        "persistence",
        "recovery_policy",
        "sidecar",
        "credential",
    } & {field.name for field in fields(CadCollaborators)}


def test_cad_dependencies_validate_required_edges() -> None:
    collaborators = rpc_server._build_cad_collaborators(
        compatibility_api=rpc_server._build_collaboration_collaborators().compatibility_api
    )
    with pytest.raises(ValueError, match="freecad"):
        replace(collaborators, freecad=None)
    with pytest.raises(TypeError, match="serialize_object"):
        replace(collaborators, serialize_object=None)
    assert collaborators.repair_references_gui is rpc_server._repair_references_gui


def test_default_cad_graph_is_eager_and_shares_native_api(monkeypatch) -> None:
    first = type(
        "FreeCADSentinel",
        (),
        {"getDocument": staticmethod(lambda _name: None)},
    )()
    monkeypatch.setattr(rpc_server, "FreeCAD", first)
    facade = rpc_server.FreeCADRPC()
    captured = facade._cad_collaborators
    monkeypatch.setattr(rpc_server, "FreeCAD", object())

    assert facade._cad_collaborators is captured
    assert captured.freecad is first
    assert captured.compatibility_api is facade._collaboration_collaborators.compatibility_api
    assert captured.compatibility_api is facade._execution_collaborators.compatibility_api
    assert "_build_cad_collaborators" not in inspect.getsource(
        rpc_server.FreeCADRPC._cad_collaborators.fget
    )


def test_explicit_cad_graph_requires_the_shared_native_api() -> None:
    collaboration = rpc_server._build_collaboration_collaborators()
    execution = rpc_server._build_execution_collaborators(
        compatibility_api=collaboration.compatibility_api
    )
    cad = rpc_server._build_cad_collaborators(
        compatibility_api=collaboration.compatibility_api
    )
    facade = rpc_server.FreeCADRPC(
        collaboration_collaborators=collaboration,
        execution_collaborators=execution,
        cad_collaborators=cad,
    )
    assert facade._cad_collaborators is cad

    with pytest.raises(TypeError, match="CadCollaborators"):
        rpc_server.FreeCADRPC(cad_collaborators=object())
    mismatched = replace(
        cad,
        compatibility_api=rpc_server._CollaborationAPI(
            document_lookup=rpc_server.FreeCAD.getDocument
        ),
    )
    with pytest.raises(ValueError, match="must share compatibility_api"):
        rpc_server.FreeCADRPC(
            collaboration_collaborators=collaboration,
            execution_collaborators=execution,
            cad_collaborators=mismatched,
        )

    mismatched_freecad = replace(cad, freecad=object())
    with pytest.raises(ValueError, match="must share freecad"):
        rpc_server.FreeCADRPC(
            collaboration_collaborators=collaboration,
            execution_collaborators=execution,
            cad_collaborators=mismatched_freecad,
        )


def test_native_cad_commit_is_exact_once_and_returns_historical_result() -> None:
    api = _NativeAPI()
    collaborators = _cad_collaborators(api)
    calls = []
    expected = {"ok": True, "object": "Pad"}

    assert run_cad_mutation(
        collaborators, "Doc", lambda: calls.append("callback") or expected
    ) is expected
    assert calls == ["callback"]
    assert len(api.calls) == 1
    assert api.calls[0][0] == "Doc"
    assert api.completed_callbacks == 1


def test_legacy_geometry_index_list_is_a_committed_success() -> None:
    api = _NativeAPI()
    expected = [2, 3, 4]
    assert run_cad_mutation(
        _cad_collaborators(api), "Doc", lambda: expected
    ) is expected
    assert len(api.calls) == 1
    assert api.completed_callbacks == 1


@pytest.mark.parametrize("failure", ["legacy failure", False, None, {"ok": False}])
def test_callback_failure_rolls_back_and_restores_legacy_envelope(failure) -> None:
    api = _NativeAPI()
    collaborators = _cad_collaborators(api)
    assert run_cad_mutation(collaborators, "Doc", lambda: failure) is failure
    assert len(api.calls) == 1
    assert api.completed_callbacks == 0


def test_native_rejection_before_or_after_callback_fails_closed() -> None:
    before = _NativeAPI(
        result={"status": "Busy", "committed": False}, invoke=False
    )
    before_calls = []
    rejected = run_cad_mutation(
        _cad_collaborators(before),
        "Doc",
        lambda: before_calls.append("callback") or True,
    )
    assert before_calls == []
    assert rejected["error_code"] == "NATIVE_COMPATIBILITY_MUTATION_REJECTED"

    after = _NativeAPI(
        result={"status": "PostconditionFailed", "committed": False}
    )
    after_calls = []
    rejected = run_cad_mutation(
        _cad_collaborators(after),
        "Doc",
        lambda: after_calls.append("callback") or True,
    )
    assert after_calls == ["callback"]
    assert rejected["success"] is False
    assert rejected["ok"] is False


def test_native_callback_health_failure_rolls_back_and_fails_closed() -> None:
    class Document:
        def __init__(self):
            self.recompute_calls = 0

        def recompute(self):
            self.recompute_calls += 1

    document = Document()
    api = _NativeAPI()
    collaborators = replace(
        _cad_collaborators(api),
        freecad=type(
            "FreeCAD",
            (),
            {"getDocument": staticmethod(lambda _name: document)},
        )(),
        validate_document_invariants=lambda _document: (_ for _ in ()).throw(
            RuntimeError("Pad")
        ),
    )

    result = run_cad_mutation(collaborators, "Doc", lambda: True)

    assert result == {
        "success": False,
        "ok": False,
        "error_code": "DOCUMENT_HEALTH_DEGRADED",
        "error": "Pad",
    }
    assert document.recompute_calls == 1
    assert api.completed_callbacks == 0


def test_missing_document_preserves_leaf_envelope_without_native_entry() -> None:
    api = _NativeAPI()
    collaborators = replace(
        _cad_collaborators(api),
        freecad=type("FreeCAD", (), {"getDocument": staticmethod(lambda _name: None)})(),
    )
    expected = "Document 'Missing' not found."
    assert run_cad_mutation(
        collaborators, "Missing", lambda: expected
    ) == expected
    assert api.calls == []


def test_document_lookup_failure_preserves_legacy_string_error() -> None:
    def failed_lookup(_name):
        raise RuntimeError("lookup failed")

    api = _NativeAPI()
    collaborators = replace(
        _cad_collaborators(api),
        freecad=type("FreeCAD", (), {"getDocument": staticmethod(failed_lookup)})(),
    )
    assert run_cad_mutation(
        collaborators, "Missing", lambda: True
    ) == "lookup failed"
    assert api.calls == []


def test_native_cad_methods_never_open_the_legacy_outer_transaction() -> None:
    assert NATIVE_COMPATIBILITY_METHODS <= NO_OUTER_TRANSACTION
    assert {
        "create_object",
        "sketch_create",
        "pad_feature",
        "spreadsheet_set_cells",
        "run_fem_analysis",
        "solve_assembly",
    } <= NATIVE_COMPATIBILITY_METHODS


def test_transaction_control_and_deferred_repair_remain_outside_native_commit() -> None:
    assert {
        "repair_references",
        "recompute_and_wait",
        "recompute_document",
        "redo",
        "undo",
    }.isdisjoint(NATIVE_COMPATIBILITY_METHODS)
    assert "repair_references" in NO_OUTER_TRANSACTION
