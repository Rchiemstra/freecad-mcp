"""Shared fakes for typed sketch execute-code unit tests."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from addon.FreeCADMCP.collaboration_api import CollaborationAPI


class FakeVector:
    def __init__(self, x: float, y: float, z: float = 0.0) -> None:
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)

    @property
    def Length(self) -> float:
        return (self.x**2 + self.y**2 + self.z**2) ** 0.5

    def __sub__(self, other: FakeVector) -> FakeVector:
        return FakeVector(self.x - other.x, self.y - other.y, self.z - other.z)


class FakeCurve:
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.poles: list[object] = []
        self.periodic = False
        self.degree = 3

    def setPoles(self, poles: list[object]) -> None:
        self.poles = list(poles)

    def interpolate(self, points: list[object], periodic: bool = False) -> None:
        self.poles = list(points)
        self.periodic = periodic

    def buildFromPoles(self, poles: list[object], periodic: bool, degree: int) -> None:
        self.poles = list(poles)
        self.periodic = periodic
        self.degree = degree

    def buildFromPolesMultsKnots(
        self,
        poles: list[object],
        multiplicities: list[int],
        knots: list[float],
        periodic: bool,
        degree: int,
        weights: list[float],
    ) -> None:
        self.poles = list(poles)
        self.periodic = periodic
        self.degree = degree
        self.multiplicities = multiplicities
        self.knots = knots
        self.weights = weights


class FakePart:
    def LineSegment(self, start: object, end: object) -> SimpleNamespace:
        return SimpleNamespace(kind="line", start=start, end=end)

    def Circle(self, center: object, normal: object, radius: float) -> SimpleNamespace:
        return SimpleNamespace(kind="circle", center=center, normal=normal, radius=radius)

    def ArcOfCircle(self, circle: object, start: float, end: float) -> SimpleNamespace:
        return SimpleNamespace(kind="arc", circle=circle, start=start, end=end)

    def Ellipse(self, major_pt: object, minor_radius: float, center: object) -> SimpleNamespace:
        return SimpleNamespace(
            kind="ellipse",
            major_pt=major_pt,
            minor_radius=minor_radius,
            center=center,
        )

    def ArcOfEllipse(self, ellipse: object, start: float, end: float) -> SimpleNamespace:
        return SimpleNamespace(kind="arc_of_ellipse", ellipse=ellipse, start=start, end=end)

    def Point(self, vector: object) -> SimpleNamespace:
        return SimpleNamespace(kind="point", vector=vector)

    def BSplineCurve(self) -> FakeCurve:
        return FakeCurve("bspline")

    def BezierCurve(self) -> FakeCurve:
        return FakeCurve("bezier")


class FakeSketcher:
    def Constraint(self, *args: object) -> SimpleNamespace:
        return SimpleNamespace(args=args)


class FakeFreeCAD:
    def Vector(self, x: float, y: float, z: float = 0.0) -> FakeVector:
        return FakeVector(x, y, z)


class FakeSketch:
    def __init__(self, name: str = "Sketch") -> None:
        self.Name = name
        self.Label = name
        self.TypeId = "Sketcher::SketchObject"
        self.Geometry: list[SimpleNamespace] = []
        self.constraints: list[object] = []
        self.trimmed: list[object] = []
        self.extended: list[object] = []
        self.split_calls: list[object] = []
        self.fillets: list[object] = []
        self.symmetries: list[object] = []
        self.fail_after_add = False
        self.fail_after_constraint = False
        self.fail_after_edit = False
        self.events: list[str] = []

    @property
    def GeometryCount(self) -> int:
        return len(self.Geometry)

    @property
    def ConstraintCount(self) -> int:
        return len(self.constraints)

    def isDerivedFrom(self, type_name: str) -> bool:
        return self.TypeId == "Sketcher::SketchObject" and type_name == "Sketcher::SketchObject"

    def addGeometry(self, geometry: object, construction: bool = False) -> int:
        index = len(self.Geometry)
        self.Geometry.append(SimpleNamespace(kind=geometry, Construction=bool(construction)))
        if not self.events or self.events[-1] != "apply":
            self.events.append("apply")
        if self.fail_after_add:
            raise RuntimeError("FreeCAD failed after mutating the sketch")
        return index

    def addConstraint(self, constraint: object) -> int:
        index = len(self.constraints)
        self.constraints.append(constraint)
        if not self.events or self.events[-1] != "apply":
            self.events.append("apply")
        if self.fail_after_constraint:
            raise RuntimeError("FreeCAD failed after mutating the sketch")
        return index

    def renameConstraint(self, index: int, name: str) -> None:
        constraint = self.constraints[index]
        constraint.name = name

    def trim(self, geo_index: int, point: object) -> None:
        self.trimmed.append((geo_index, point))
        if not self.events or self.events[-1] != "apply":
            self.events.append("apply")
        if self.fail_after_edit:
            raise RuntimeError("FreeCAD failed after mutating the sketch")

    def extend(self, geo_index: int, increment: float, end_point: int) -> None:
        self.extended.append((geo_index, increment, end_point))
        if not self.events or self.events[-1] != "apply":
            self.events.append("apply")
        if self.fail_after_edit:
            raise RuntimeError("FreeCAD failed after mutating the sketch")

    def split(self, geo_index: int, point: object) -> None:
        self.split_calls.append((geo_index, point))
        if not self.events or self.events[-1] != "apply":
            self.events.append("apply")
        if self.fail_after_edit:
            raise RuntimeError("FreeCAD failed after mutating the sketch")

    def fillet(
        self,
        geo1: int,
        geo2: int,
        point1: object,
        point2: object,
        radius: float,
        trim: bool,
        create_point: bool,
    ) -> None:
        self.fillets.append((geo1, geo2, radius, trim, create_point))
        if not self.events or self.events[-1] != "apply":
            self.events.append("apply")
        if self.fail_after_edit:
            raise RuntimeError("FreeCAD failed after mutating the sketch")

    def addSymmetric(self, indices: list[int], symmetry_geo: int) -> None:
        self.symmetries.append((list(indices), symmetry_geo))
        if not self.events or self.events[-1] != "apply":
            self.events.append("apply")
        if self.fail_after_edit:
            raise RuntimeError("FreeCAD failed after mutating the sketch")

    def toggleConstruction(self, geo_index: int) -> None:
        geom = self.Geometry[geo_index]
        geom.Construction = not bool(geom.Construction)
        if not self.events or self.events[-1] != "apply":
            self.events.append("apply")
        if self.fail_after_edit:
            raise RuntimeError("FreeCAD failed after mutating the sketch")


class FakeDocument:
    Name = "Doc"

    def __init__(self, events: list[str], sketch: FakeSketch | None = None) -> None:
        self.events = events
        self.objects: dict[str, Any] = {}
        self.recomputed = False
        self.add_calls = 0
        if sketch is None:
            sketch = FakeSketch()
        sketch.events = self.events
        self.objects[sketch.Name] = sketch
        self.sketch = sketch

    def getObject(self, name: str) -> object | None:
        item = self.objects.get(name)
        if item is not None and self.recomputed:
            self.events.append("inspect")
        return item

    def addObject(self, object_type: str, name: str) -> SimpleNamespace:
        self.add_calls += 1
        obj = SimpleNamespace(Name=name, TypeId=object_type, Label=name)
        self.objects[name] = obj
        return obj

    def recompute(self) -> None:
        self.events.append("recompute")
        self.recomputed = True


class MutateThenRaiseDocument(FakeDocument):
    def __init__(self, events: list[str], sketch: FakeSketch | None = None) -> None:
        super().__init__(events, sketch)
        self.sketch.fail_after_add = True
        self.sketch.fail_after_constraint = True
        self.sketch.fail_after_edit = True


class RecomputeFailureDocument(FakeDocument):
    def recompute(self) -> None:
        super().recompute()
        raise RuntimeError("FreeCAD recompute failed")


class MissingAfterRecomputeDocument(FakeDocument):
    def recompute(self) -> None:
        super().recompute()
        self.objects.clear()


class ReplacingAfterRecomputeDocument(FakeDocument):
    def recompute(self) -> None:
        super().recompute()
        self.objects[self.sketch.Name] = FakeSketch(self.sketch.Name)


class WrongTypeAfterRecomputeDocument(FakeDocument):
    def recompute(self) -> None:
        super().recompute()
        self.sketch.TypeId = "Part::Feature"


class NativeBridgeDocument(FakeDocument):
    def commitCompatibilityMutation(self, callback, *, structural=False, postcondition=None):
        assert structural is True
        before_objects = dict(self.objects)
        before_geom = list(self.sketch.Geometry)
        before_constraints = list(self.sketch.constraints)
        before_recomputed = self.recomputed
        try:
            callback()
            self.recompute()
            if postcondition is not None and not postcondition():
                self.objects = before_objects
                self.sketch.Geometry = before_geom
                self.sketch.constraints = before_constraints
                self.recomputed = before_recomputed
                self.events.append("abort")
                return {"status": "PostconditionFailed", "committed": False}
        except Exception:
            self.objects = before_objects
            self.sketch.Geometry = before_geom
            self.sketch.constraints = before_constraints
            self.recomputed = before_recomputed
            self.events.append("abort")
            return {"status": "ApplyFailed", "committed": False}
        self.events.append("commit")
        return {"status": "Committed", "committed": True}


class CompatibilityAPI:
    def __init__(self, document: FakeDocument | None, *, final_result=None) -> None:
        self.document = document
        self.final_result = final_result
        self.calls: list[tuple[object, ...]] = []

    def _restore(self, objects: dict[str, Any], recomputed: bool, geom: list[Any], constraints: list[Any]) -> None:
        assert self.document is not None
        self.document.objects = objects
        self.document.recomputed = recomputed
        self.document.sketch.Geometry = geom
        self.document.sketch.constraints = constraints
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
        before_geom = list(self.document.sketch.Geometry)
        before_constraints = list(self.document.sketch.constraints)
        try:
            callback(self.document) if bind_document else callback()
        except Exception as exc:
            self._restore(before_objects, before_recomputed, before_geom, before_constraints)
            return {"status": "ApplyFailed", "committed": False, "message": str(exc)}

        try:
            self.document.recompute()
        except Exception as exc:
            self._restore(before_objects, before_recomputed, before_geom, before_constraints)
            return {
                "status": "RecomputeFailed",
                "committed": False,
                "rollback_succeeded": True,
                "message": str(exc),
            }

        if postcondition is not None:
            satisfied = postcondition(self.document) if bind_document else postcondition()
            if not satisfied:
                self._restore(before_objects, before_recomputed, before_geom, before_constraints)
                return {
                    "status": "PostconditionFailed",
                    "committed": False,
                    "rollback_succeeded": True,
                }

        if self.final_result is not None:
            result = dict(self.final_result)
            if not result.get("committed"):
                self._restore(before_objects, before_recomputed, before_geom, before_constraints)
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


def collaborators(
    document: FakeDocument | None,
    events: list[str],
    *,
    validator=None,
    final_result=None,
):
    api = CompatibilityAPI(document, final_result=final_result)
    collab = SimpleNamespace(
        freecad=FakeFreeCAD(),
        part=FakePart(),
        sketcher=FakeSketcher(),
        validate_document_invariants=(
            validator if validator is not None else lambda _document: events.append("validate")
        ),
        commit_native_mutation=api.commit_native_mutation,
    )
    return collab, api


def native_bridge_collaborators(document: FakeDocument, events: list[str], lookup=None):
    bridge = CollaborationAPI(document_lookup=lookup or (lambda _name: document))
    return SimpleNamespace(
        freecad=FakeFreeCAD(),
        part=FakePart(),
        sketcher=FakeSketcher(),
        validate_document_invariants=lambda _document: events.append("validate"),
        commit_native_mutation=bridge.commit_native_mutation,
    )
