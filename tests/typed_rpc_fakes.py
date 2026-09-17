"""Shared doubles for typed core/document mutation unit tests."""

from __future__ import annotations

from types import SimpleNamespace

from addon.FreeCADMCP.collaboration_api import CollaborationAPI


class FakeObject:
    def __init__(self, name: str, type_id: str = "Part::Feature") -> None:
        self.Name = name
        self.Label = name
        self.TypeId = type_id
        self.OutList: list[FakeObject] = []
        self.PropertiesList = ["Label"]
        self._prop_types: dict[str, str] = {"Label": "App::PropertyString"}

    def getTypeIdOfProperty(self, name: str) -> str:
        return self._prop_types.get(name, "App::PropertyString")

    def isDerivedFrom(self, type_name: str) -> bool:
        return self.TypeId == type_name


class FakeDocument:
    def __init__(self, events: list[str], name: str = "Doc") -> None:
        self.Name = name
        self.Label = name
        self.FileName = f"{name}.FCStd"
        self.events = events
        self.objects: dict[str, FakeObject] = {}
        self.recomputed = False
        self.add_calls = 0
        self.UndoCount = 1
        self.RedoCount = 1

    @property
    def Objects(self) -> list[FakeObject]:
        return list(self.objects.values())

    def getObject(self, name: str) -> FakeObject | None:
        obj = self.objects.get(name)
        if obj is not None and self.recomputed:
            self.events.append("inspect")
        return obj

    def addObject(self, object_type: str, name: str) -> FakeObject:
        self.add_calls += 1
        self.events.append("apply")
        obj = FakeObject(name, object_type)
        self.objects[name] = obj
        return obj

    def removeObject(self, name: str) -> None:
        self.events.append("apply")
        self.objects.pop(name, None)

    def undo(self) -> None:
        self.events.append("apply")

    def redo(self) -> None:
        self.events.append("apply")

    def recompute(self) -> None:
        self.events.append("recompute")
        self.recomputed = True


class CompatibilityAPI:
    def __init__(self, document: FakeDocument | None, *, final_result=None, events: list[str] | None = None) -> None:
        self.document = document
        self.final_result = final_result
        self.calls: list[tuple[object, ...]] = []
        self.documents: dict[str, FakeDocument] = {}
        self.events = events if events is not None else (document.events if document is not None else [])
        if document is not None:
            self.documents[document.Name] = document

    def _restore(self, objects, recomputed) -> None:
        assert self.document is not None
        self.document.objects = objects
        self.document.recomputed = recomputed
        self.document.events.append("abort")

    def commit_compatibility_mutation(
        self,
        document_name,
        callback,
        *,
        structural=False,
        postcondition=None,
        bind_document=False,
        require_native=False,
    ):
        self.calls.append((document_name, structural, bind_document, require_native))
        if self.document is None:
            raise LookupError("document_lookup returned no document")
        before_objects = dict(self.document.objects)
        before_recomputed = self.document.recomputed
        try:
            callback(self.document) if bind_document else callback()
        except Exception as exc:
            self._restore(before_objects, before_recomputed)
            return {"status": "ApplyFailed", "committed": False, "message": str(exc)}
        try:
            self.document.recompute()
        except Exception as exc:
            self._restore(before_objects, before_recomputed)
            return {
                "status": "RecomputeFailed",
                "committed": False,
                "rollback_succeeded": True,
                "message": str(exc),
            }
        if postcondition is not None:
            satisfied = postcondition(self.document) if bind_document else postcondition()
            if not satisfied:
                self._restore(before_objects, before_recomputed)
                return {
                    "status": "PostconditionFailed",
                    "committed": False,
                    "rollback_succeeded": True,
                }
        if self.final_result is not None:
            result = dict(self.final_result)
            if not result.get("committed"):
                self._restore(before_objects, before_recomputed)
            return result
        self.document.events.append("commit")
        return {"status": "Committed", "committed": True}

    def commit_native_mutation(
        self, document_name, callback, postcondition, *, structural=True
    ):
        return self.commit_compatibility_mutation(
            document_name,
            callback,
            structural=structural,
            postcondition=postcondition,
            bind_document=True,
            require_native=True,
        )

    def newDocument(self, name: str) -> FakeDocument:
        document = FakeDocument(self.events, name=name)
        self.document = document
        self.documents[name] = document
        return document

    def openDocument(self, path: str) -> FakeDocument:
        from pathlib import Path as PathLib

        name = PathLib(path).stem or "Opened"
        return self.newDocument(name)

    def closeDocument(self, name: str) -> None:
        self.documents.pop(name, None)
        if self.document is not None and self.document.Name == name:
            self.document = None

    def getDocument(self, name: str) -> FakeDocument | None:
        if self.document is not None and self.document.Name == name:
            return self.document
        return self.documents.get(name)

    def setActiveDocument(self, name: str) -> None:
        document = self.getDocument(name)
        if document is not None:
            self.document = document


def collaborators(
    document: FakeDocument | None,
    events: list[str],
    *,
    validator=None,
    final_result=None,
):
    api = CompatibilityAPI(document, final_result=final_result, events=events)

    def set_active_document(name: str) -> None:
        api.setActiveDocument(name)
        app.ActiveDocument = api.getDocument(name)

    app = SimpleNamespace(
        getDocument=api.getDocument,
        newDocument=api.newDocument,
        openDocument=api.openDocument,
        closeDocument=api.closeDocument,
        setActiveDocument=set_active_document,
        ActiveDocument=document,
    )
    def _serialize_object(obj: FakeObject) -> dict[str, object]:
        return {
            "Name": obj.Name,
            "Label": obj.Label,
            "TypeId": obj.TypeId,
        }

    collab = SimpleNamespace(
        freecad=app,
        validate_document_invariants=(
            validator if validator is not None else lambda _document: events.append("validate")
        ),
        commit_native_mutation=api.commit_native_mutation,
        serialize_object=_serialize_object,
        set_object_property=lambda _doc, obj, properties: [
            setattr(obj, key, value) for key, value in properties.items()
        ],
        insert_part_from_library=lambda doc_name, relative_path: (
            api.getDocument(doc_name).addObject("Part::Feature", "LibraryPart")
            if api.getDocument(doc_name) is not None
            else None
        ),
    )
    return collab, api


def native_bridge_collaborators(document: FakeDocument, events: list[str]):
    bridge = CollaborationAPI(document_lookup=lambda _name: document)
    return SimpleNamespace(
        validate_document_invariants=lambda _document: events.append("validate"),
        commit_native_mutation=bridge.commit_native_mutation,
        freecad=SimpleNamespace(getDocument=lambda _name: document),
    )


__all__ = [
    "CompatibilityAPI",
    "FakeDocument",
    "FakeObject",
    "collaborators",
    "native_bridge_collaborators",
]
