"""Unit coverage for the typed ``delete_object`` mutation slice."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.collaboration_api import CollaborationAPI
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.delete_object import (
    apply_delete_object,
    run_delete_object,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.delete_object_mutation import (
    _delete_object_native_result,
    _NativeMutationState,
)
from tests.typed_rpc_fakes import FakeDocument, collaborators

pytestmark = pytest.mark.unit


def test_delete_object_runs_apply_recompute_validate_then_commits():
    events: list[str] = []
    document = FakeDocument(events)
    document.addObject('Part::Feature', 'Box')
    document.events.clear()
    collab, _api = collaborators(document, events)

    result = run_delete_object(collab, "Doc", "Box", False, False)

    assert result["success"] is True
    assert result['object_name'] == 'Box'
    assert "recompute" in events
    assert "validate" in events
    assert "commit" in events


def test_invalid_arguments_abort_without_commit():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)

    result = run_delete_object(collab, "Doc", "", False, False)

    assert result["success"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"
    assert "commit" not in events


def test_missing_document_fails_without_entering_apply():
    events: list[str] = []
    collab, _api = collaborators(None, events)
    if "delete_object" in {"create_document", "open_document"}:
        pytest.skip("lifecycle create/open allocate a document before native commit")

    result = run_delete_object(collab, "Doc", "Box", False, False)

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
    assert events == []


def test_native_capability_is_required_before_apply():
    events: list[str] = []
    registry: dict[str, FakeDocument] = {}
    if "delete_object" not in {"create_document", "open_document"}:
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

    result = run_delete_object(collab, "Doc", "Box", False, False)

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

    result = run_delete_object(collab, "Doc", "Box", False, False)

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
    result = _delete_object_native_result(native_result, _NativeMutationState(postcondition_passed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["retry_safe"] is False


def test_delete_object_has_apply_entry_point():
    assert callable(apply_delete_object)


class _TipBody:
    """A PartDesign Body that moves its Tip only through Body.removeObject."""

    TypeId = "PartDesign::Body"

    def __init__(self, log: list[str]) -> None:
        self.Name = "Body"
        self.InList: list[object] = []
        self.Group: list[object] = []
        self.Tip: object | None = None
        self._log = log

    def isDerivedFrom(self, type_id: str) -> bool:
        return type_id == self.TypeId

    def removeObject(self, feature: object) -> list[object]:
        self._log.append(f"Body.removeObject({feature.Name})")
        index = self.Group.index(feature)
        if self.Tip is feature:
            self.Tip = self.Group[index - 1] if index else None
        self.Group.remove(feature)
        return []


class _BodyDocument:
    def __init__(self, objects: list[object], log: list[str]) -> None:
        self._objects = {item.Name: item for item in objects}
        self._log = log

    def getObject(self, name: str) -> object | None:
        return self._objects.get(name)

    def removeObject(self, name: str) -> None:
        self._log.append(f"Document.removeObject({name})")
        self._objects.pop(name)


def test_deleting_the_tip_feature_moves_the_body_tip_back():
    """Document.removeObject knows nothing about bodies.

    FreeCAD's own delete calls Body.removeObject first so the Tip moves to the
    previous solid. Without it, MCP left Tip empty and the whole Body had a
    null shape although its first pad was intact.
    """

    log: list[str] = []
    body = _TipBody(log)

    def feature(name: str) -> SimpleNamespace:
        item = SimpleNamespace(Name=name, TypeId="PartDesign::Pad", InList=[body])
        item.isDerivedFrom = lambda type_id: type_id == item.TypeId
        item.getParentGeoFeatureGroup = lambda: body
        return item

    first, second = feature("PadMain"), feature("PadDup")
    body.Group = [first, second]
    body.Tip = second
    document = _BodyDocument([body, first, second], log)
    request = SimpleNamespace(object_name="PadDup", recursive=False, force=False)

    receipt = apply_delete_object(document, request)

    assert receipt.deleted == ("PadDup",)
    assert body.Tip is first
    assert log == ["Body.removeObject(PadDup)", "Document.removeObject(PadDup)"]


def _hole_with_dependents(events):
    document = FakeDocument(events)
    hole = document.addObject("PartDesign::Pocket", "Hole")
    for name in ("Mirror", "Pattern"):
        dependent = document.addObject("PartDesign::Mirrored", name)
        dependent.OutList.append(hole)
        hole.InList.append(dependent)
    document.events.clear()
    return document


def test_refusal_is_a_rejection_that_lists_the_dependents():
    """A refusal deletes nothing, so it must not read as a commit."""

    events: list[str] = []
    document = _hole_with_dependents(events)
    collab, _api = collaborators(document, events)

    result = run_delete_object(collab, "Doc", "Hole", False, False)

    assert result["success"] is False
    assert result["ok"] is False
    assert result["committed"] is False
    assert result["outcome"] == "rejected"
    assert result["error_code"] == "OBJECT_HAS_DEPENDENTS"
    assert "Mirror" in result["error"] and "Pattern" in result["error"]
    assert result["retry_safe"] is True
    diagnostics = result["diagnostics"]
    assert diagnostics["refused"] is True
    assert [item["name"] for item in diagnostics["dependents"]] == ["Mirror", "Pattern"]
    assert set(document.objects) == {"Hole", "Mirror", "Pattern"}
    assert "commit" not in events


def test_force_reports_the_orphans_it_leaves():
    events: list[str] = []
    document = _hole_with_dependents(events)
    collab, _api = collaborators(document, events)

    result = run_delete_object(collab, "Doc", "Hole", False, True)

    assert result["success"] is True
    assert result["deleted"] == ["Hole"]
    assert [item["name"] for item in result["orphans_left"]] == ["Mirror", "Pattern"]
    assert set(document.objects) == {"Mirror", "Pattern"}


def test_recursive_delete_leaves_no_orphans():
    events: list[str] = []
    document = _hole_with_dependents(events)
    collab, _api = collaborators(document, events)

    result = run_delete_object(collab, "Doc", "Hole", True, False)

    assert result["success"] is True
    assert sorted(result["deleted"]) == ["Hole", "Mirror", "Pattern"]
    assert "orphans_left" not in result
    assert document.objects == {}
