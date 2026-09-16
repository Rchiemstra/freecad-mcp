"""Typed ``sketch_add_regular_polygon`` mutation."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.sketch_add_regular_polygon_contract import (
    SketchAddRegularPolygonCollaborators,
    SketchAddRegularPolygonFailure,
    SketchAddRegularPolygonRequest,
    SketchAddRegularPolygonResult,
    DocumentName,
    SketchDocument,
    SketchName,
    SketchObject,
    SketchReadDocument,
    make_sketch_add_regular_polygon_failure,
    make_sketch_add_regular_polygon_success,
    make_sketch_add_regular_polygon_uncertain,
)
from .sketch_add_regular_polygon_mutation import SketchAddRegularPolygonError, run_sketch_add_regular_polygon_native_mutation


@dataclass(frozen=True, slots=True)
class SketchExecReceipt:
    name: str
    sketch: SketchObject
    geometry_index: int
    geometry_count_before: int
    constraint_count_before: int
    sample_count: int


@dataclass(frozen=True, slots=True)
class SketchExecInspection:
    sketch_name: SketchName
    geometry_index: int
    geometry_indices: list[int]
    constraint_index: int
    sample_count: int


def _failure(error: SketchAddRegularPolygonError, *, retry_safe: bool = True) -> SketchAddRegularPolygonFailure:
    return make_sketch_add_regular_polygon_failure(error.code, str(error), retry_safe=retry_safe)


def _require_name(value: object, field: str) -> str | SketchAddRegularPolygonFailure:
    if not isinstance(value, str) or not value.strip():
        return _failure(SketchAddRegularPolygonError("INVALID_ARGUMENT", f"{field} must be a nonempty string"))
    return value


def _require_float(value: object, field: str) -> float | SketchAddRegularPolygonFailure:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _failure(SketchAddRegularPolygonError("INVALID_ARGUMENT", f"{field} must be a number"))
    return float(value)


def _require_int(value: object, field: str) -> int | SketchAddRegularPolygonFailure:
    if type(value) is not int:
        return _failure(SketchAddRegularPolygonError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_bool(value: object, field: str, *, default: bool) -> bool | SketchAddRegularPolygonFailure:
    if value is None:
        return default
    if type(value) is not bool:
        return _failure(SketchAddRegularPolygonError("INVALID_ARGUMENT", f"{field} must be a boolean"))
    return value


def _require_optional_int(value: object, field: str) -> int | None | SketchAddRegularPolygonFailure:
    if value is None:
        return None
    if type(value) is not int:
        return _failure(SketchAddRegularPolygonError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_optional_str(value: object, field: str) -> str | None | SketchAddRegularPolygonFailure:
    if value is None:
        return None
    if not isinstance(value, str):
        return _failure(SketchAddRegularPolygonError("INVALID_ARGUMENT", f"{field} must be a string"))
    return value


def _require_points(
    value: object, field: str, *, min_count: int
) -> tuple[tuple[float, float], ...] | SketchAddRegularPolygonFailure:
    if not isinstance(value, list):
        return _failure(SketchAddRegularPolygonError("INVALID_ARGUMENT", f"{field} must be a list of points"))
    points: list[tuple[float, float]] = []
    for item in value:
        if not isinstance(item, dict):
            return _failure(SketchAddRegularPolygonError("INVALID_ARGUMENT", f"{field} entries must be objects"))
        x_value = _require_float(item.get("x"), f"{field}.x")
        y_value = _require_float(item.get("y"), f"{field}.y")
        if isinstance(x_value, dict):
            return x_value
        if isinstance(y_value, dict):
            return y_value
        points.append((x_value, y_value))
    if len(points) < min_count:
        return _failure(SketchAddRegularPolygonError("INVALID_ARGUMENT", f"{field} requires at least {min_count} points"))
    return tuple(points)


def _require_int_list(value: object, field: str) -> tuple[int, ...] | SketchAddRegularPolygonFailure:
    if not isinstance(value, list) or not value:
        return _failure(SketchAddRegularPolygonError("INVALID_ARGUMENT", f"{field} must be a nonempty list of integers"))
    indices: list[int] = []
    for item in value:
        parsed = _require_int(item, field)
        if isinstance(parsed, dict):
            return parsed
        indices.append(parsed)
    return tuple(indices)


def _require_optional_floats(value: object, field: str) -> tuple[float, ...] | None | SketchAddRegularPolygonFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchAddRegularPolygonError("INVALID_ARGUMENT", f"{field} must be a list of numbers"))
    numbers: list[float] = []
    for item in value:
        parsed = _require_float(item, field)
        if isinstance(parsed, dict):
            return parsed
        numbers.append(parsed)
    return tuple(numbers)


def _require_optional_ints(value: object, field: str) -> tuple[int, ...] | None | SketchAddRegularPolygonFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchAddRegularPolygonError("INVALID_ARGUMENT", f"{field} must be a list of integers"))
    numbers: list[int] = []
    for item in value:
        parsed = _require_int(item, field)
        if isinstance(parsed, dict):
            return parsed
        numbers.append(parsed)
    return tuple(numbers)


def _is_sketch(sketch: SketchObject) -> bool:
    try:
        return bool(sketch.isDerivedFrom("Sketcher::SketchObject"))
    except (AttributeError, TypeError):
        return sketch.TypeId == "Sketcher::SketchObject"


def _require_sketch(doc: SketchDocument, sketch_name: SketchName) -> SketchObject:
    sketch = doc.getObject(sketch_name)
    if sketch is None:
        raise SketchAddRegularPolygonError("SKETCH_NOT_FOUND", f"Sketch not found: {sketch_name!r}")
    if not _is_sketch(sketch):
        raise SketchAddRegularPolygonError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {sketch_name!r}")
    return sketch

def build_sketch_add_regular_polygon_request(doc_name: object, sketch_name: object, cx: object, cy: object, radius: object, sides: object, angle: object, construction: object) -> SketchAddRegularPolygonRequest | SketchAddRegularPolygonFailure:
    doc_name_value = _require_name(doc_name, 'doc_name')
    if isinstance(doc_name_value, dict):
        return doc_name_value
    sketch_name_value = _require_name(sketch_name, 'sketch_name')
    if isinstance(sketch_name_value, dict):
        return sketch_name_value
    cx_value = _require_float(cx, 'cx')
    if isinstance(cx_value, dict):
        return cx_value
    cy_value = _require_float(cy, 'cy')
    if isinstance(cy_value, dict):
        return cy_value
    radius_value = _require_float(radius, 'radius')
    if isinstance(radius_value, dict):
        return radius_value
    sides_value = _require_int(sides, 'sides')
    if isinstance(sides_value, dict):
        return sides_value
    angle_value = _require_float(angle, 'angle')
    if isinstance(angle_value, dict):
        return angle_value
    construction_value = _require_bool(construction, 'construction', default=False)
    if isinstance(construction_value, dict):
        return construction_value
    if sides_value < 3:
        return _failure(SketchAddRegularPolygonError("INVALID_ARGUMENT", "regular polygon requires at least 3 sides"))
    return SketchAddRegularPolygonRequest(
        doc_name=DocumentName(doc_name_value),
        sketch_name=SketchName(sketch_name_value),
        cx=cx_value,
        cy=cy_value,
        radius=radius_value,
        sides=sides_value,
        angle=angle_value,
        construction=construction_value,
    )

def apply_sketch_add_regular_polygon(
    doc: SketchDocument,
    request: SketchAddRegularPolygonRequest,
    collaborators: SketchAddRegularPolygonCollaborators,
) -> SketchExecReceipt:
    """Mutate the sketch without recomputing or managing a transaction."""

    sketch = _require_sketch(doc, request.sketch_name)
    before_geo = sketch.GeometryCount
    before_con = sketch.ConstraintCount
    offset = math.radians(request.angle)
    pts = [
        collaborators.freecad.Vector(
            request.cx + request.radius * math.cos(offset + 2 * math.pi * index / request.sides),
            request.cy + request.radius * math.sin(offset + 2 * math.pi * index / request.sides),
            0.0,
        )
        for index in range(request.sides)
    ]
    last = -1
    for index in range(request.sides):
        last = int(
            sketch.addGeometry(
                collaborators.part.LineSegment(pts[index], pts[(index + 1) % request.sides]),
                request.construction,
            )
        )
    return SketchExecReceipt(
        name=sketch.Name,
        sketch=sketch,
        geometry_index=last,
        geometry_count_before=before_geo,
        constraint_count_before=before_con,
        sample_count=0,
    )

def read_sketch_add_regular_polygon_result(doc: SketchReadDocument, receipt: SketchExecReceipt) -> SketchExecInspection:
    sketch = doc.getObject(receipt.name)
    if sketch is None:
        raise SketchAddRegularPolygonError("SKETCH_MISSING", f"Sketch is missing: {receipt.name!r}")
    if sketch is not receipt.sketch:
        raise SketchAddRegularPolygonError("SKETCH_REPLACED", f"Sketch was replaced before commit: {receipt.name!r}")
    if not _is_sketch(sketch):
        raise SketchAddRegularPolygonError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {receipt.name!r}")
    if sketch.GeometryCount <= receipt.geometry_count_before:
        raise SketchAddRegularPolygonError(
            "GEOMETRY_MISSING",
            f"Created sketch geometry is missing: {receipt.name!r}",
        )
    indices = list(range(receipt.geometry_count_before, sketch.GeometryCount))
    return SketchExecInspection(
        sketch_name=SketchName(receipt.name),
        geometry_index=receipt.geometry_index,
        geometry_indices=indices,
        constraint_index=receipt.geometry_index,
        sample_count=receipt.sample_count,
    )


@dataclass(slots=True)
class _SketchAddRegularPolygonExecution:
    collaborators: SketchAddRegularPolygonCollaborators
    request: SketchAddRegularPolygonRequest
    created: SketchExecReceipt | None = None
    inspected: SketchExecInspection | None = None

    def apply(self, doc: SketchDocument) -> None:
        self.created = apply_sketch_add_regular_polygon(doc, self.request, self.collaborators)

    def inspect(self, doc: SketchReadDocument) -> None:
        if self.created is None:
            raise SketchAddRegularPolygonError(
                "INVALID_SKETCH_ADD_REGULAR_POLYGON_RESULT",
                "sketch_add_regular_polygon did not return an identity receipt",
            )
        self.inspected = read_sketch_add_regular_polygon_result(doc, self.created)

    def run(self) -> SketchAddRegularPolygonResult:
        result = run_sketch_add_regular_polygon_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_add_regular_polygon_uncertain(
                "SKETCH_ADD_REGULAR_POLYGON_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected sketch_add_regular_polygon result",
                committed=True,
            )
        return make_sketch_add_regular_polygon_success(SketchName(self.inspected.sketch_name), self.inspected.geometry_indices)


def run_sketch_add_regular_polygon(
    collaborators: SketchAddRegularPolygonCollaborators,
    doc_name: object, sketch_name: object, cx: object, cy: object, radius: object, sides: object, angle: object, construction: object,
) -> SketchAddRegularPolygonResult:
    request = build_sketch_add_regular_polygon_request(doc_name, sketch_name, cx, cy, radius, sides, angle, construction)
    if isinstance(request, dict):
        return request
    return _SketchAddRegularPolygonExecution(collaborators, request).run()


class _SketchAddRegularPolygonRpcFacade(Protocol):
    _cad_collaborators: SketchAddRegularPolygonCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sketch_add_regular_polygon(
    self: _SketchAddRegularPolygonRpcFacade, doc_name: str, sketch_name: str, cx: float, cy: float, radius: float, sides: int, angle: float = 0.0, construction: bool = False,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_add_regular_polygon(collaborators, doc_name, sketch_name, cx, cy, radius, sides, angle, construction)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_add_regular_polygon", rpc_sketch_add_regular_polygon)


__all__ = [
    "SketchAddRegularPolygonCollaborators",
    "SketchAddRegularPolygonError",
    "apply_sketch_add_regular_polygon",
    "build_sketch_add_regular_polygon_request",
    "read_sketch_add_regular_polygon_result",
    "rpc_sketch_add_regular_polygon",
    "run_sketch_add_regular_polygon",
    "TYPED_RPC_HANDLER",
]
