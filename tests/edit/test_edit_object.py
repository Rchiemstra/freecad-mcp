"""Unit coverage for the typed ``edit_object`` mutation slice."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.collaboration_api import CollaborationAPI
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.edit_object import (
    apply_edit_object,
    run_edit_object,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.edit_object_mutation import (
    _edit_object_native_result,
    _NativeMutationState,
)
from tests.typed_rpc_fakes import FakeDocument, collaborators

pytestmark = pytest.mark.unit


def test_edit_object_runs_apply_recompute_validate_then_commits():
    events: list[str] = []
    document = FakeDocument(events)
    document.addObject('Part::Feature', 'Box')
    document.events.clear()
    collab, _api = collaborators(document, events)

    result = run_edit_object(collab, "Doc", "Box", {"Properties": {"Label": "Edited"}})

    assert result["success"] is True
    assert result['object_name'] == 'Box'
    assert "recompute" in events
    assert "validate" in events
    assert "commit" in events


def test_invalid_arguments_abort_without_commit():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)

    result = run_edit_object(collab, "Doc", "", {})

    assert result["success"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"
    assert "commit" not in events


def test_missing_document_fails_without_entering_apply():
    events: list[str] = []
    collab, _api = collaborators(None, events)
    if "edit_object" in {"create_document", "open_document"}:
        pytest.skip("lifecycle create/open allocate a document before native commit")

    result = run_edit_object(collab, "Doc", "Box", {"Properties": {"Label": "Edited"}})

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
    assert events == []


def test_native_capability_is_required_before_apply():
    events: list[str] = []
    registry: dict[str, FakeDocument] = {}
    if "edit_object" not in {"create_document", "open_document"}:
        seeded = FakeDocument(events)
        seeded.addObject('Part::Feature', 'Box')
        seeded.events.clear()
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

    result = run_edit_object(collab, "Doc", "Box", {"Properties": {"Label": "Edited"}})

    assert result["success"] is False
    assert result["native_status"] == "Unsupported"


def test_native_rejection_never_returns_cached_success():
    events: list[str] = []
    document = FakeDocument(events)
    document.addObject('Part::Feature', 'Box')
    document.events.clear()
    collab, _api = collaborators(
        document,
        events,
        final_result={"status": "PublicationFailed", "committed": False},
    )

    result = run_edit_object(collab, "Doc", "Box", {"Properties": {"Label": "Edited"}})

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
    result = _edit_object_native_result(native_result, _NativeMutationState(postcondition_passed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["retry_safe"] is False


def test_edit_object_has_apply_entry_point():
    assert callable(apply_edit_object)


def test_inspection_rejects_reverted_label_after_recompute():
    events: list[str] = []

    class _RevertLabel(FakeDocument):
        def recompute(self) -> None:
            super().recompute()
            box = self.objects.get("Box")
            if box is not None:
                box.Label = "Box"

    document = _RevertLabel(events)
    document.addObject("Part::Feature", "Box")
    document.events.clear()
    collab, _api = collaborators(document, events)
    result = run_edit_object(collab, "Doc", "Box", {"Properties": {"Label": "Edited"}})
    assert result["success"] is False
    assert result["error_code"] == "PROPERTY_NOT_UPDATED"
    assert "commit" not in events
