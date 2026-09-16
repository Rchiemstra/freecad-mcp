"""Shared document doubles for typed G-features-p3 unit tests."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from addon.FreeCADMCP.collaboration_api import CollaborationAPI


class FeatureObj:
    def __init__(self, name: str, type_id: str, document: FeatureDocument | None = None) -> None:
        self.Name = name
        self.Label = f"Label for {name}"
        self.TypeId = type_id
        self.Visibility = True
        self.Group: list[object] = []
        self.PropertiesList = [
            "Originals",
            "Original",
            "Length",
            "Occurrences",
            "Direction",
            "Reversed",
            "Angle",
            "Axis",
            "MirrorPlane",
            "Plane",
            "Profile",
            "Spine",
            "Frenet",
            "Sections",
            "Ruled",
            "Closed",
            "Pitch",
            "Height",
            "Radius",
            "LeftHanded",
            "Base",
            "Tool",
            "ReferenceAxis",
            "Symmetric",
            "Size",
        ]
        self.Origin = SimpleNamespace(OriginFeatures=[])
        self.Tip = None
        self.Shape = SimpleNamespace(isNull=lambda: False, Faces=[object()], Volume=1.0)
        self._document = document

    def isDerivedFrom(self, type_name: str) -> bool:
        return self.TypeId == type_name or self.TypeId.startswith(type_name)

    def newObject(self, object_type: str, name: str) -> FeatureObj:
        assert self._document is not None
        child = self._document.register_object(object_type, name, event="apply")
        self.Group.append(child)
        return child


class FeatureDocument:
    Name = "Doc"

    def __init__(self, events: list[str], *, assigned_name: str | None = None) -> None:
        self.events = events
        self.objects: dict[str, FeatureObj] = {}
        self.assigned_name = assigned_name
        self.recomputed = False
        self.add_calls = 0
        for axis in ("X_Axis", "Y_Axis", "Z_Axis", "XY_Plane", "XZ_Plane", "YZ_Plane"):
            self.objects[axis] = FeatureObj(axis, "App::OriginFeature", self)

    def getObject(self, name: str) -> FeatureObj | None:
        obj = self.objects.get(name)
        if obj is not None and self.recomputed:
            self.events.append("inspect")
        return obj

    def register_object(self, object_type: str, name: str, *, event: str | None = "apply") -> FeatureObj:
        self.add_calls += 1
        if event is not None:
            self.events.append(event)
        actual_name = self.assigned_name or name
        obj = FeatureObj(actual_name, object_type, self)
        self.objects[actual_name] = obj
        return obj

    def addObject(self, object_type: str, name: str) -> FeatureObj:
        return self.register_object(object_type, name)

    def recompute(self) -> None:
        self.events.append("recompute")
        self.recomputed = True

    @property
    def Objects(self) -> list[FeatureObj]:
        return list(self.objects.values())


class MissingAfterRecomputeDocument(FeatureDocument):
    def recompute(self) -> None:
        super().recompute()
        created = [name for name in self.objects if name not in {
            "X_Axis", "Y_Axis", "Z_Axis", "XY_Plane", "XZ_Plane", "YZ_Plane",
            "Shape1", "Shape2", "Pad", "Body", "Sketch", "Sketch1", "Sketch2", "Path",
        }]
        for name in created:
            self.objects.pop(name, None)


class ReplacingAfterRecomputeDocument(FeatureDocument):
    def __init__(self, events: list[str], created_name: str, **kwargs: Any) -> None:
        super().__init__(events, **kwargs)
        self.created_name = created_name

    def recompute(self) -> None:
        super().recompute()
        self.objects[self.created_name] = FeatureObj(self.created_name, "App::FeaturePython", self)


class WrongTypeAfterRecomputeDocument(FeatureDocument):
    def __init__(self, events: list[str], created_name: str, **kwargs: Any) -> None:
        super().__init__(events, **kwargs)
        self.created_name = created_name

    def recompute(self) -> None:
        super().recompute()
        if self.created_name in self.objects:
            self.objects[self.created_name].TypeId = "App::FeaturePython"


class MutateThenRaiseDocument(FeatureDocument):
    def register_object(self, object_type: str, name: str, *, event: str | None = "apply") -> FeatureObj:
        obj = super().register_object(object_type, name, event=event)
        raise RuntimeError("FreeCAD failed after creating the feature")


class RecomputeFailureDocument(FeatureDocument):
    def recompute(self) -> None:
        super().recompute()
        raise RuntimeError("FreeCAD recompute failed")


class NativeBridgeDocument(FeatureDocument):
    def commitCompatibilityMutation(self, callback, *, structural=False, postcondition=None):
        assert structural is True
        before_objects = dict(self.objects)
        before_recomputed = self.recomputed
        try:
            callback()
            self.recompute()
            if postcondition is not None and not postcondition():
                self.objects = before_objects
                self.recomputed = before_recomputed
                self.events.append("abort")
                return {"status": "PostconditionFailed", "committed": False}
        except Exception:
            self.objects = before_objects
            self.recomputed = before_recomputed
            self.events.append("abort")
            return {"status": "ApplyFailed", "committed": False}
        self.events.append("commit")
        return {"status": "Committed", "committed": True}


class CompatibilityAPI:
    def __init__(self, document: FeatureDocument | None, *, final_result=None) -> None:
        self.document = document
        self.final_result = final_result
        self.calls: list[tuple[object, ...]] = []

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

    def commit_native_mutation(self, document_name, callback, postcondition, *, structural=True):
        return self.commit_compatibility_mutation(
            document_name,
            callback,
            structural=structural,
            postcondition=postcondition,
            bind_document=True,
            require_native=True,
        )


def prepare_document(kind: str, document: FeatureDocument) -> None:
    if kind == "boolean":
        document.objects["Shape1"] = FeatureObj("Shape1", "Part::Box", document)
        document.objects["Shape2"] = FeatureObj("Shape2", "Part::Box", document)
        return
    body = FeatureObj("Body", "PartDesign::Body", document)
    document.objects["Body"] = body
    if kind == "edge_feature" or kind == "pattern":
        pad = FeatureObj("Pad", "PartDesign::Pad", document)
        document.objects["Pad"] = pad
        body.Group.append(pad)
        return
    if kind == "profile":
        sketch = FeatureObj("Sketch", "Sketcher::SketchObject", document)
        document.objects["Sketch"] = sketch
        body.Group.append(sketch)
        return
    if kind == "loft":
        sketch1 = FeatureObj("Sketch1", "Sketcher::SketchObject", document)
        sketch2 = FeatureObj("Sketch2", "Sketcher::SketchObject", document)
        document.objects["Sketch1"] = sketch1
        document.objects["Sketch2"] = sketch2
        body.Group.extend([sketch1, sketch2])
        return
    if kind == "sweep":
        sketch = FeatureObj("Sketch", "Sketcher::SketchObject", document)
        path = FeatureObj("Path", "Sketcher::SketchObject", document)
        document.objects["Sketch"] = sketch
        document.objects["Path"] = path
        body.Group.extend([sketch, path])
        return
    raise KeyError(kind)


def collaborators(document: FeatureDocument | None, events: list[str], *, validator=None, final_result=None):
    api = CompatibilityAPI(document, final_result=final_result)
    return SimpleNamespace(
        validate_document_invariants=(
            validator if validator is not None else lambda _document: events.append("validate")
        ),
        commit_native_mutation=api.commit_native_mutation,
    ), api


def production_bridge_collaborators(document: FeatureDocument, events: list[str]):
    bridge = CollaborationAPI(document_lookup=lambda _name: document)
    return SimpleNamespace(
        validate_document_invariants=lambda _document: events.append("validate"),
        commit_native_mutation=bridge.commit_native_mutation,
    )
