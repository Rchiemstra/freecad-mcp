"""Typed ``sketch_add_geometry`` mutation."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.sketch_add_geometry_contract import (
    DocumentName,
    SketchAddGeometryCollaborators,
    SketchAddGeometryDocument,
    SketchAddGeometryFailure,
    SketchAddGeometryObject,
    SketchAddGeometryReadDocument,
    SketchAddGeometryResult,
    SketchName,
    make_sketch_add_geometry_failure,
    make_sketch_add_geometry_success,
    make_sketch_add_geometry_uncertain,
)
from .sketch_add_geometry_mutation import (
    SketchAddGeometryError,
    run_sketch_add_geometry_native_mutation,
)


@dataclass(frozen=True, slots=True)
class SketchAddGeometryReceipt:
    name: str
    sketch: SketchAddGeometryObject
    indices: tuple[int, ...]
    geometry_count_before: int


@dataclass(frozen=True, slots=True)
class SketchAddGeometryInspection:
    name: SketchName
    indices: list[int]


@dataclass(frozen=True, slots=True, kw_only=True)
class _SketchAddGeometryRequest:
    doc_name: DocumentName
    sketch_name: SketchName
    geometry: tuple[Mapping[str, object], ...]


def _failure(
    error: SketchAddGeometryError, *, retry_safe: bool = True
) -> SketchAddGeometryFailure:
    return make_sketch_add_geometry_failure(error.code, str(error), retry_safe=retry_safe)


def _geometry_count(sketch: object) -> int:
    count = getattr(sketch, "GeometryCount", None)
    if isinstance(count, int) and not isinstance(count, bool):
        return count
    return len(getattr(sketch, "Geometry", []) or [])


def _number(value: object, field: str, default: float | None = None) -> float:
    if value is None and default is not None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SketchAddGeometryError("INVALID_ARGUMENT", f"{field} must be a number")
    return float(value)


def _point(value: object, field: str) -> tuple[float, float]:
    if not isinstance(value, Mapping):
        raise SketchAddGeometryError("INVALID_ARGUMENT", f"{field} must be an object")
    return _number(value.get("x", 0), f"{field}.x", 0.0), _number(value.get("y", 0), f"{field}.y", 0.0)


def _add_item(sketch: object, geom: Mapping[str, object], freecad: object, part: object) -> list[int]:
    geom_type_obj = geom.get("type", "")
    geom_type = geom_type_obj.lower() if isinstance(geom_type_obj, str) else ""
    construction = bool(geom.get("construction", False))
    vector = getattr(freecad, "Vector")
    add_geometry = getattr(sketch, "addGeometry")
    if geom_type == "line":
        if "start" not in geom or "end" not in geom:
            raise SketchAddGeometryError(
                "INVALID_ARGUMENT",
                "line geometry requires start and end points",
            )
        start_x, start_y = _point(geom["start"], "start")
        end_x, end_y = _point(geom["end"], "end")
        segment = getattr(part, "LineSegment")(vector(start_x, start_y, 0), vector(end_x, end_y, 0))
        return [int(add_geometry(segment, construction))]
    if geom_type == "circle":
        center_x, center_y = _point(geom.get("center", {"x": 0, "y": 0}), "center")
        radius = _number(geom.get("radius", 1), "radius", 1.0)
        circle = getattr(part, "Circle")(vector(center_x, center_y, 0), vector(0, 0, 1), radius)
        return [int(add_geometry(circle, construction))]
    if geom_type == "arc":
        center_x, center_y = _point(geom.get("center", {"x": 0, "y": 0}), "center")
        radius = _number(geom.get("radius", 1), "radius", 1.0)
        start_angle = _number(geom.get("start_angle", 0), "start_angle", 0.0)
        end_angle = _number(geom.get("end_angle", 90), "end_angle", 90.0)
        base = getattr(part, "Circle")(vector(center_x, center_y, 0), vector(0, 0, 1), radius)
        arc = getattr(part, "ArcOfCircle")(base, math.radians(start_angle), math.radians(end_angle))
        return [int(add_geometry(arc, construction))]
    if geom_type == "rectangle":
        x1 = _number(geom.get("x1", 0), "x1", 0.0)
        y1 = _number(geom.get("y1", 0), "y1", 0.0)
        x2 = _number(geom.get("x2", 10), "x2", 10.0)
        y2 = _number(geom.get("y2", 10), "y2", 10.0)
        corners = (
            (vector(x1, y1, 0), vector(x2, y1, 0)),
            (vector(x2, y1, 0), vector(x2, y2, 0)),
            (vector(x2, y2, 0), vector(x1, y2, 0)),
            (vector(x1, y2, 0), vector(x1, y1, 0)),
        )
        line_segment = getattr(part, "LineSegment")
        return [int(add_geometry(line_segment(p1, p2), construction)) for p1, p2 in corners]
    if geom_type == "point":
        x = _number(geom.get("x", 0), "x", 0.0)
        y = _number(geom.get("y", 0), "y", 0.0)
        point = getattr(part, "Point")(vector(x, y, 0))
        return [int(add_geometry(point, construction))]
    raise SketchAddGeometryError("INVALID_ARGUMENT", f"Unknown geometry type: {geom_type!r}")


def apply_sketch_add_geometry(
    doc: SketchAddGeometryDocument,
    sketch_name: SketchName,
    geometry: Sequence[Mapping[str, object]],
    collaborators: SketchAddGeometryCollaborators,
) -> SketchAddGeometryReceipt:
    """Add sketch geometry without recomputing or managing a transaction."""

    sketch = doc.getObject(sketch_name)
    if sketch is None:
        raise SketchAddGeometryError("SKETCH_NOT_FOUND", f"Sketch {sketch_name!r} not found")
    if not hasattr(sketch, "addGeometry"):
        raise SketchAddGeometryError("NOT_A_SKETCH", f"Object {sketch_name!r} is not an editable sketch")
    geometry_count_before = _geometry_count(sketch)
    indices: list[int] = []
    for item in geometry:
        indices.extend(_add_item(sketch, item, collaborators.freecad, collaborators.part))
    return SketchAddGeometryReceipt(
        name=sketch.Name,
        sketch=sketch,
        indices=tuple(indices),
        geometry_count_before=geometry_count_before,
    )


def read_sketch_add_geometry_result(
    doc: SketchAddGeometryReadDocument, receipt: SketchAddGeometryReceipt
) -> SketchAddGeometryInspection:
    sketch = doc.getObject(receipt.name)
    if sketch is None:
        raise SketchAddGeometryError("CREATED_OBJECT_MISSING", f"Sketch is missing: {receipt.name!r}")
    if sketch is not receipt.sketch:
        raise SketchAddGeometryError(
            "CREATED_OBJECT_REPLACED",
            f"Sketch was replaced before commit: {receipt.name!r}",
        )
    if _geometry_count(sketch) <= receipt.geometry_count_before:
        raise SketchAddGeometryError(
            "GEOMETRY_NOT_ADDED",
            f"Sketch geometry count did not increase on {receipt.name!r}",
        )
    return SketchAddGeometryInspection(name=SketchName(receipt.name), indices=list(receipt.indices))


def build_sketch_add_geometry_request(
    doc_name: object, sketch_name: object, geometry: object
) -> _SketchAddGeometryRequest | SketchAddGeometryFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(SketchAddGeometryError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(sketch_name, str) or not sketch_name.strip():
        return _failure(
            SketchAddGeometryError("INVALID_ARGUMENT", "sketch_name must be a nonempty string")
        )
    if not isinstance(geometry, list) or not geometry:
        return _failure(SketchAddGeometryError("INVALID_ARGUMENT", "geometry must be a non-empty list"))
    items: list[Mapping[str, object]] = []
    for item in geometry:
        if not isinstance(item, Mapping) or any(not isinstance(key, str) for key in item):
            return _failure(SketchAddGeometryError("INVALID_ARGUMENT", "geometry items must be objects"))
        items.append({str(key): item[key] for key in item})
    return _SketchAddGeometryRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        geometry=tuple(items),
    )


@dataclass(slots=True)
class _SketchAddGeometryExecution:
    collaborators: SketchAddGeometryCollaborators
    request: _SketchAddGeometryRequest
    created: SketchAddGeometryReceipt | None = None
    inspected: SketchAddGeometryInspection | None = None

    def apply(self, doc: SketchAddGeometryDocument) -> None:
        self.created = apply_sketch_add_geometry(
            doc, self.request.sketch_name, self.request.geometry, self.collaborators
        )

    def inspect(self, doc: SketchAddGeometryReadDocument) -> None:
        if self.created is None:
            raise SketchAddGeometryError(
                "INVALID_SKETCH_ADD_GEOMETRY_RESULT",
                "Geometry add did not return an identity receipt",
            )
        self.inspected = read_sketch_add_geometry_result(doc, self.created)

    def run(self) -> SketchAddGeometryResult:
        result = run_sketch_add_geometry_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_add_geometry_uncertain(
                "SKETCH_ADD_GEOMETRY_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected geometry result",
                committed=True,
            )
        return make_sketch_add_geometry_success(self.inspected.name, self.inspected.indices)


def run_sketch_add_geometry(
    collaborators: SketchAddGeometryCollaborators,
    doc_name: object,
    sketch_name: object,
    geometry: object,
) -> SketchAddGeometryResult:
    request = build_sketch_add_geometry_request(doc_name, sketch_name, geometry)
    if isinstance(request, dict):
        return request
    return _SketchAddGeometryExecution(collaborators, request).run()


class _SketchAddGeometryRpcFacade(Protocol):
    _cad_collaborators: SketchAddGeometryCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sketch_add_geometry(
    self: _SketchAddGeometryRpcFacade,
    doc_name: str,
    sketch_name: str,
    geometry: object,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_add_geometry(collaborators, doc_name, sketch_name, geometry)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_add_geometry", rpc_sketch_add_geometry)


__all__ = [
    "SketchAddGeometryCollaborators",
    "SketchAddGeometryError",
    "SketchAddGeometryInspection",
    "SketchAddGeometryReceipt",
    "apply_sketch_add_geometry",
    "build_sketch_add_geometry_request",
    "read_sketch_add_geometry_result",
    "rpc_sketch_add_geometry",
    "run_sketch_add_geometry",
    "TYPED_RPC_HANDLER",
]
