"""Unit coverage for the typed ``activate_document`` mutation slice."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.collaboration_api import CollaborationAPI
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.activate_document import (
    apply_activate_document,
    run_activate_document,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.activate_document_mutation import (
    _activate_document_native_result,
    _NativeMutationState,
)
from tests.typed_rpc_fakes import FakeDocument, collaborators

pytestmark = pytest.mark.unit


def test_activate_document_runs_apply_recompute_validate_then_commits():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)

    result = run_activate_document(collab, "Doc")

    assert result["success"] is True
    assert result['document_name'] == 'Doc'
    assert "recompute" in events
    assert "validate" in events
    assert "commit" in events


def test_invalid_arguments_abort_without_commit():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)

    result = run_activate_document(collab, "")

    assert result["success"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"
    assert "commit" not in events


def test_missing_document_fails_without_entering_apply():
    events: list[str] = []
    collab, _api = collaborators(None, events)
    if "activate_document" in {"create_document", "open_document"}:
        pytest.skip("lifecycle create/open allocate a document before native commit")

    result = run_activate_document(collab, "Doc")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
    assert events == []


def test_native_capability_is_required_before_apply():
    events: list[str] = []
    registry: dict[str, FakeDocument] = {}
    if "activate_document" not in {"create_document", "open_document"}:
        seeded = FakeDocument(events)
        registry[seeded.Name] = seeded

    def get_document(lookup_name: str):
        return registry.get(lookup_name)

    def new_document(created_name: str):
        created = FakeDocument(events, name=created_name)
        registry[created_name] = created
        return created

    def open_document(path: str):
        created_name = path.rsplit("/", 1)[-1].removesuffix(".FCStd") or "Opened"
        return new_document(created_name)

    def close_document(closed_name: str):
        registry.pop(closed_name, None)

    bridge = CollaborationAPI(document_lookup=get_document)
    collab = SimpleNamespace(
        freecad=SimpleNamespace(
            getDocument=get_document,
            newDocument=new_document,
            openDocument=open_document,
            closeDocument=close_document,
            setActiveDocument=lambda _name: None,
        ),
        validate_document_invariants=lambda _document: events.append("validate"),
        commit_native_mutation=bridge.commit_native_mutation,
        insert_part_from_library=lambda doc_name, relative_path: (
            registry[doc_name].addObject("Part::Feature", "LibraryPart")
            if doc_name in registry
            else None
        ),
        set_object_property=lambda _doc, obj, properties: [
            setattr(obj, key, value) for key, value in properties.items()
        ],
    )

    result = run_activate_document(collab, "Doc")

    assert result["success"] is False
    assert result["native_status"] == "Unsupported"


def test_native_rejection_never_returns_cached_success():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(
        document,
        events,
        final_result={"status": "PublicationFailed", "committed": False},
    )

    result = run_activate_document(collab, "Doc")

    assert result["success"] is False
    assert result["error_code"] in {
        "NATIVE_COMPATIBILITY_MUTATION_REJECTED",
        "CREATE_DOCUMENT_ROLLBACK_UNCERTAIN",
        "OPEN_DOCUMENT_ROLLBACK_UNCERTAIN",
    }


@pytest.mark.parametrize(
    "native_result",
    [
        None,
        {},
        {"status": "FutureStatus", "committed": False},
        {"status": "Committed", "committed": False},
        {"status": "Busy", "committed": True},
        {"status": "Committed", "committed": True, "rollback_succeeded": True},
    ],
)
def test_unknown_or_contradictory_native_evidence_cannot_release_success(native_result):
    result = _activate_document_native_result(native_result, _NativeMutationState(postcondition_passed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["retry_safe"] is False


def test_activate_document_has_apply_entry_point():
    assert callable(apply_activate_document)
