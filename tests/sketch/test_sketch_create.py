
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from addon.FreeCADMCP.collaboration_api import CollaborationAPI
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import sketch_create as subject
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_create import (
    run_sketch_create,
)

pytestmark = pytest.mark.unit


class _Vector:
    def __init__(self, x, y, z=0) -> None:
        self.x, self.y, self.z = x, y, z


class _Part:
    class Circle:
        def __init__(self, center, normal, radius) -> None:
            self.center, self.normal, self.radius = center, normal, radius

    class LineSegment:
        def __init__(self, start, end) -> None:
            self.start, self.end = start, end

    class ArcOfCircle:
        def __init__(self, base, start, end) -> None:
            self.base, self.start, self.end = base, start, end

    class Point:
        def __init__(self, vector) -> None:
            self.vector = vector


class _ConstraintType:
    def __init__(self, *args) -> None:
        self.args = args
        self.Name = ""


class _Shape:
    def isClosed(self):
        return True

    def isNull(self):
        return False


def _target(name: str, type_id: str):
    return SimpleNamespace(Name=name, Label=f"Label for {name}", TypeId=type_id)


class _Document:
    Name = "Doc"

    def __init__(self, events: list[str], *, assigned_name: str | None = None, fail_after_apply: bool = False) -> None:
        self.events = events
        self.objects: dict[str, Any] = {}
        self.assigned_name = assigned_name
        self.recomputed = False
        self.add_calls = 0
        self.fail_after_apply = fail_after_apply
        _seed(self, 'empty')

    def getObject(self, name):
        obj = self.objects.get(name)
        if obj is not None and self.recomputed and "inspect" not in self.events:
            self.events.append("inspect")
        return obj

    def addObject(self, object_type, name):
        self.add_calls += 1
        self.events.append("apply")
        actual_name = self.assigned_name or name
        obj = _target(actual_name, object_type)
        obj.Shape = _Shape()
        self.objects[actual_name] = obj
        if self.fail_after_apply:
            raise RuntimeError("FreeCAD failed after mutating the document")
        return obj

    def recompute(self):
        self.events.append("recompute")
        self.recomputed = True

    @property
    def Objects(self):
        return list(self.objects.values())


class _OriginPlane:
    def __init__(self, name: str, label: str) -> None:
        self.Name = name
        self.Label = label


class _Origin:
    TypeId = "App::Origin"

    def __init__(self) -> None:
        self.OriginFeatures = [
            _OriginPlane("XY_Plane", "XY_Plane"),
            _OriginPlane("XZ_Plane", "XZ_Plane"),
            _OriginPlane("YZ_Plane", "YZ_Plane"),
        ]


class _Body:
    def __init__(self, document: _Document, name: str) -> None:
        self.Name = name
        self.Label = name
        self.TypeId = "PartDesign::Body"
        self.Group: list[Any] = []
        self.Tip = None
        self.Origin = _Origin()
        self._document = document

    def isDerivedFrom(self, type_name: str) -> bool:
        return type_name == "PartDesign::Body"

    def newObject(self, object_type, name):
        self._document.add_calls += 1
        self._document.events.append("apply")
        actual_name = self._document.assigned_name or name
        if object_type == "Sketcher::SketchObject":
            obj = _Sketch(self._document, actual_name)
        else:
            obj = _target(actual_name, object_type)
            obj.Shape = _Shape()
            obj.Profile = None
            obj.Length = None
        self.Group.append(obj)
        self._document.objects[actual_name] = obj
        if self._document.fail_after_apply:
            raise RuntimeError("FreeCAD failed after mutating the document")
        return obj


class _Sketch:
    def __init__(self, document: _Document, name: str = "Sketch") -> None:
        self.Name = name
        self.Label = f"Label for {name}"
        self.TypeId = "Sketcher::SketchObject"
        self.MapMode = ""
        self.AttachmentOffset = object()
        self.Geometry: list[Any] = [object(), object()]
        self.Constraints = [SimpleNamespace(Name="R"), SimpleNamespace(Name="Extra")]
        self.ConflictingConstraints: list[Any] = []
        self.MalformedConstraints: list[Any] = []
        self.Shape = _Shape()
        self._document = document
        self._support = None

    @property
    def AttachmentSupport(self):
        return self._support

    @AttachmentSupport.setter
    def AttachmentSupport(self, value):
        self._document.events.append("apply")
        self._support = value
        if self._document.fail_after_apply:
            raise RuntimeError("FreeCAD failed after mutating the document")

    def addGeometry(self, geom, construction=False):
        if "apply" not in self._document.events:
            self._document.events.append("apply")
        self.Geometry.append(geom)
        if self._document.fail_after_apply:
            raise RuntimeError("FreeCAD failed after mutating the document")
        return len(self.Geometry) - 1

    def addConstraint(self, constraint):
        if "apply" not in self._document.events:
            self._document.events.append("apply")
        self.Constraints.append(constraint)
        if self._document.fail_after_apply:
            raise RuntimeError("FreeCAD failed after mutating the document")
        return len(self.Constraints) - 1

    def renameConstraint(self, index, name):
        self.Constraints[index].Name = name

    def delGeometries(self, indices):
        if "apply" not in self._document.events:
            self._document.events.append("apply")
        for index in sorted(set(indices), reverse=True):
            del self.Geometry[index]
        if self._document.fail_after_apply:
            raise RuntimeError("FreeCAD failed after mutating the document")

    def delConstraints(self, indices, _remove_dependent=True):
        if "apply" not in self._document.events:
            self._document.events.append("apply")
        for index in sorted(set(indices), reverse=True):
            del self.Constraints[index]
        if self._document.fail_after_apply:
            raise RuntimeError("FreeCAD failed after mutating the document")

    def setDatum(self, index, value):
        if "apply" not in self._document.events:
            self._document.events.append("apply")
        self.Constraints[index].value = value
        if self._document.fail_after_apply:
            raise RuntimeError("FreeCAD failed after mutating the document")


def _seed(document: _Document, mode: str) -> None:
    if mode == "empty":
        return
    sketch = _Sketch(document)
    document.objects["Sketch"] = sketch
    if mode in {"pad", "pocket", "attach"}:
        body = _Body(document, "Body")
        body.Group = [sketch]
        document.objects["Body"] = body
    if mode == "attach":
        document.objects["Box"] = _target("Box", "Part::Box")


class _MissingAfterRecomputeDocument(_Document):
    def recompute(self):
        super().recompute()
        self.objects.clear()


class _ReplacingAfterRecomputeDocument(_Document):
    def recompute(self):
        super().recompute()
        name = 'Sketch'
        if name in self.objects:
            self.objects[name] = _target(name, self.objects[name].TypeId)


class _WrongTypeAfterRecomputeDocument(_Document):
    def recompute(self):
        super().recompute()
        name = 'Sketch'
        if name in self.objects:
            self.objects[name].TypeId = "Part::Feature"


class _MutateThenRaiseDocument(_Document):
    def __init__(self, events: list[str], **kwargs) -> None:
        super().__init__(events, fail_after_apply=True, **kwargs)


class _RecomputeFailureDocument(_Document):
    def recompute(self):
        super().recompute()
        raise RuntimeError("FreeCAD recompute failed")


class _NativeBridgeDocument(_Document):
    def commitCompatibilityMutation(self, callback, *, structural=False, postcondition=None, recompute=True):
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


class _CompatibilityAPI:
    def __init__(self, document: _Document | None, *, final_result=None) -> None:
        self.document = document
        self.final_result = final_result
        self.calls = []

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


def _collaborators(document: _Document | None, events: list[str], *, validator=None, final_result=None):
    api = _CompatibilityAPI(document, final_result=final_result)
    collaborators = SimpleNamespace(
        freecad=SimpleNamespace(
            getDocument=lambda name: (
                document if document is not None and name == document.Name else None
            ),
            Vector=_Vector,
        ),
        part=_Part,
        sketcher=SimpleNamespace(Constraint=_ConstraintType),
        dict_to_placement=lambda value: value,
        placement_to_dict=lambda value: value,
        set_extrusion_symmetric=lambda feature, value: setattr(feature, "Midplane", value),
        set_feature_bool=lambda feature, names, value: setattr(feature, names[0], value),
        validate_document_invariants=(
            validator if validator is not None else lambda _document: events.append("validate")
        ),
        commit_native_mutation=api.commit_native_mutation,
    )
    return collaborators, api


def _call(collaborators, *extra):
    if extra:
        args = list(('Doc', 'Sketch'))
        args[1] = extra[0]
        return run_sketch_create(collaborators, *tuple(args))
    return run_sketch_create(collaborators, *('Doc', 'Sketch'))


def test_sketch_create_runs_apply_recompute_inspect_validate_then_commits():
    events = []
    document = _Document(events)
    collaborators, api = _collaborators(document, events)

    result = _call(collaborators)

    assert result["success"] is True
    assert result["ok"] is True
    assert result["outcome"] == "committed"
    assert result["committed"] is True
    assert result["retry_safe"] is False
    assert result["sketch"] == "Sketch"
    assert result["label"] == "Label for Sketch"
    assert events == ["apply", "recompute", "inspect", "validate", "commit"]
    assert api.calls == [("Doc", True, True, True)]


@pytest.mark.parametrize("invalid", [None, 42, [], {}, "", " ", "\t\r\n"])
def test_invalid_names_abort_without_recompute_or_commit(invalid):
    events = []
    document = _Document(events)
    collaborators, _api = _collaborators(document, events)

    result = _call(collaborators, invalid)

    assert result["success"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"
    assert "recompute" not in events
    assert "commit" not in events


def test_missing_document_fails_without_entering_the_apply_callback():
    events = []
    collaborators, api = _collaborators(None, events)

    result = _call(collaborators)

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
    assert api.calls == [("Doc", True, True, True)]
    assert events == []


def test_duplicate_or_missing_target_aborts_without_recompute_or_commit():
    events = []
    document = _Document(events)
    existing = _target("Sketch", "Sketcher::SketchObject")
    document.objects["Sketch"] = existing
    collaborators, _api = _collaborators(document, events)

    result = _call(collaborators)

    assert result["success"] is False
    assert result["error_code"] == 'OBJECT_ALREADY_EXISTS'
    assert "recompute" not in events
    assert "commit" not in events


def test_creation_that_changes_then_raises_is_rolled_back():
    events = []
    document = _MutateThenRaiseDocument(events)
    collaborators, _api = _collaborators(document, events)

    result = _call(collaborators)

    assert result["success"] is False
    assert result["error_code"] == 'SKETCH_CREATE_FAILED'
    assert "commit" not in events
    assert "abort" in events


def test_recompute_failure_is_rolled_back():
    events = []
    document = _RecomputeFailureDocument(events)
    collaborators, _api = _collaborators(document, events)

    result = _call(collaborators)

    assert result["success"] is False
    assert result["error_code"] == "NATIVE_COMPATIBILITY_MUTATION_REJECTED"
    assert result["native_status"] == "RecomputeFailed"
    assert result["rollback_succeeded"] is True
    assert events == ["apply", "recompute", "abort"]


def test_failed_validation_aborts_before_commit():
    events = []
    document = _Document(events)

    def fail_validation(_document):
        events.append("validate")
        raise RuntimeError("document health degraded")

    collaborators, _api = _collaborators(document, events, validator=fail_validation)

    result = _call(collaborators)

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_HEALTH_DEGRADED"
    assert events == ["apply", "recompute", "inspect", "validate", "abort"]


def test_native_rejection_never_returns_cached_success():
    events = []
    document = _Document(events)
    collaborators, _api = _collaborators(
        document,
        events,
        final_result={"status": "PublicationFailed", "committed": False},
    )

    result = _call(collaborators)

    assert result["success"] is False
    assert result["error_code"] == "NATIVE_COMPATIBILITY_MUTATION_REJECTED"
    assert result["native_status"] == "PublicationFailed"
    assert events == ["apply", "recompute", "inspect", "validate", "abort"]


def test_native_capability_is_required_before_apply():
    events = []
    document = _Document(events)
    bridge = CollaborationAPI(document_lookup=lambda _name: document)
    collaborators = SimpleNamespace(
        freecad=SimpleNamespace(getDocument=lambda _name: document, Vector=_Vector),
        part=_Part,
        sketcher=SimpleNamespace(Constraint=_ConstraintType),
        dict_to_placement=lambda value: value,
        placement_to_dict=lambda value: value,
        set_extrusion_symmetric=lambda feature, value: None,
        set_feature_bool=lambda feature, names, value: None,
        validate_document_invariants=lambda _document: events.append("validate"),
        commit_native_mutation=bridge.commit_native_mutation,
    )

    result = _call(collaborators)

    assert result["success"] is False
    assert result["native_status"] == "Unsupported"
    assert document.add_calls == 0
    assert events == []


def test_native_rollback_failure_remains_distinguishable():
    events = []
    document = _Document(events)
    collaborators, _api = _collaborators(
        document,
        events,
        final_result={
            "status": "RollbackFailed",
            "committed": False,
            "rollback_succeeded": False,
        },
    )

    result = _call(collaborators)

    assert result["success"] is False
    assert result["native_status"] == "RollbackFailed"
    assert result["rollback_succeeded"] is False


@pytest.mark.parametrize(
    ("document_type", "error_code"),
    [(_MissingAfterRecomputeDocument, 'CREATED_OBJECT_MISSING'), (_ReplacingAfterRecomputeDocument, 'CREATED_OBJECT_REPLACED'), (_WrongTypeAfterRecomputeDocument, 'CREATED_OBJECT_WRONG_TYPE')],
)
def test_inspection_rejects_missing_replaced_or_wrong_type(document_type, error_code):
    events = []
    document = document_type(events)
    collaborators, _api = _collaborators(document, events)

    result = _call(collaborators)

    assert result["success"] is False
    assert result["error_code"] == error_code
    assert "commit" not in events


def test_apply_and_inspect_use_the_native_admitted_document():
    events = []
    admitted = _NativeBridgeDocument(events)
    other = _NativeBridgeDocument([])
    lookups = []

    def changing_lookup(name):
        lookups.append(name)
        return admitted if len(lookups) == 1 else other

    bridge = CollaborationAPI(document_lookup=changing_lookup)
    collaborators = SimpleNamespace(
        freecad=SimpleNamespace(Vector=_Vector),
        part=_Part,
        sketcher=SimpleNamespace(Constraint=_ConstraintType),
        dict_to_placement=lambda value: value,
        placement_to_dict=lambda value: value,
        set_extrusion_symmetric=lambda feature, value: setattr(feature, "Midplane", value),
        set_feature_bool=lambda feature, names, value: setattr(feature, names[0], value),
        validate_document_invariants=lambda _document: events.append("validate"),
        commit_native_mutation=bridge.commit_native_mutation,
    )

    result = _call(collaborators)

    assert result["success"] is True
    assert lookups == ["Doc"]
    assert events == ["apply", "recompute", "inspect", "validate", "commit"]


def test_response_uses_the_actual_name_assigned_by_freecad():
    events = []
    document = _Document(events, assigned_name='Sketch001')
    collaborators, _api = _collaborators(document, events)

    result = _call(collaborators)

    assert result["success"] is True
    assert result["sketch"] == "Sketch001"


def test_body_owned_create_with_attach_to_uses_body_origin():
    events = []
    document = _Document(events)
    body = _Body(document, "Body")
    document.objects["Body"] = body
    collaborators, _api = _collaborators(document, events)

    result = run_sketch_create(collaborators, "Doc", "BodySketch", "Body", "XY_Plane")

    assert result["success"] is True
    sketch = document.objects["BodySketch"]
    assert sketch.AttachmentSupport[0][0] in body.Origin.OriginFeatures
    assert sketch.MapMode == "FlatFace"


def test_sketch_create_has_no_uncoordinated_source_entry_point():
    assert not hasattr(subject, 'sketch_create_gui')


@pytest.mark.parametrize(
    "native_result",
    [
        None,
        {},
        {"status": "FutureStatus", "committed": False},
        {"status": "Committed", "committed": False},
        {"status": "Busy", "committed": True},
        {"status": "Committed", "committed": 1},
        {"status": "Committed", "committed": True, "rollback_failed": True},
        {"status": "Committed", "committed": True, "rollback_succeeded": True},
        {"status": "Committed", "committed": True, "rollback_failed": "false"},
    ],
)
def test_unknown_or_contradictory_native_evidence_cannot_release_success(native_result):
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_create_mutation import (
        _sketch_create_native_result,
        _NativeSketchCreateMutationState,
    )

    result = _sketch_create_native_result(native_result, _NativeSketchCreateMutationState(postcondition_passed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["retry_safe"] is False


def test_exception_after_native_apply_does_not_claim_rollback():
    events = []
    document = _Document(events)

    def native_exception(_name, apply, _postcondition, **_kwargs):
        apply(document)
        raise RuntimeError("native result unavailable")

    collaborators = SimpleNamespace(
        freecad=SimpleNamespace(Vector=_Vector),
        part=_Part,
        sketcher=SimpleNamespace(Constraint=_ConstraintType),
        dict_to_placement=lambda value: value,
        placement_to_dict=lambda value: value,
        set_extrusion_symmetric=lambda feature, value: setattr(feature, "Midplane", value),
        set_feature_bool=lambda feature, names, value: setattr(feature, names[0], value),
        commit_native_mutation=native_exception,
        validate_document_invariants=lambda _: None,
    )
    result = _call(collaborators)
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False
