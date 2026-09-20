"""Typed ``sketch_add_polyline`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

try:
    from ...._shared.protocol.sketch_add_polyline_contract import (
        SketchAddPolylineCollaborators,
        SketchAddPolylineFailure,
        SketchAddPolylineRequest,
        SketchAddPolylineResult,
        DocumentName,
        SketchDocument,
        SketchName,
        SketchObject,
        SketchReadDocument,
        make_sketch_add_polyline_failure,
        make_sketch_add_polyline_success,
        make_sketch_add_polyline_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.sketch_add_polyline_contract import (
        SketchAddPolylineCollaborators,
        SketchAddPolylineFailure,
        SketchAddPolylineRequest,
        SketchAddPolylineResult,
        DocumentName,
        SketchDocument,
        SketchName,
        SketchObject,
        SketchReadDocument,
        make_sketch_add_polyline_failure,
        make_sketch_add_polyline_success,
        make_sketch_add_polyline_uncertain,
    )
from .sketch_add_polyline_mutation import SketchAddPolylineError, run_sketch_add_polyline_native_mutation


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


def _failure(error: SketchAddPolylineError, *, retry_safe: bool = True) -> SketchAddPolylineFailure:
    return make_sketch_add_polyline_failure(error.code, str(error), retry_safe=retry_safe)


def _require_name(value: object, field: str) -> str | SketchAddPolylineFailure:
    if not isinstance(value, str) or not value.strip():
        return _failure(SketchAddPolylineError("INVALID_ARGUMENT", f"{field} must be a nonempty string"))
    return value


def _require_float(value: object, field: str) -> float | SketchAddPolylineFailure:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _failure(SketchAddPolylineError("INVALID_ARGUMENT", f"{field} must be a number"))
    return float(value)


def _require_int(value: object, field: str) -> int | SketchAddPolylineFailure:
    if type(value) is not int:
        return _failure(SketchAddPolylineError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_bool(value: object, field: str, *, default: bool) -> bool | SketchAddPolylineFailure:
    if value is None:
        return default
    if type(value) is not bool:
        return _failure(SketchAddPolylineError("INVALID_ARGUMENT", f"{field} must be a boolean"))
    return value


def _require_optional_int(value: object, field: str) -> int | None | SketchAddPolylineFailure:
    if value is None:
        return None
    if type(value) is not int:
        return _failure(SketchAddPolylineError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_optional_str(value: object, field: str) -> str | None | SketchAddPolylineFailure:
    if value is None:
        return None
    if not isinstance(value, str):
        return _failure(SketchAddPolylineError("INVALID_ARGUMENT", f"{field} must be a string"))
    return value


def _require_points(
    value: object, field: str, *, min_count: int
) -> tuple[tuple[float, float], ...] | SketchAddPolylineFailure:
    if not isinstance(value, list):
        return _failure(SketchAddPolylineError("INVALID_ARGUMENT", f"{field} must be a list of points"))
    points: list[tuple[float, float]] = []
    for item in value:
        if not isinstance(item, dict):
            return _failure(SketchAddPolylineError("INVALID_ARGUMENT", f"{field} entries must be objects"))
        x_value = _require_float(item.get("x"), f"{field}.x")
        y_value = _require_float(item.get("y"), f"{field}.y")
        if isinstance(x_value, dict):
            return x_value
        if isinstance(y_value, dict):
            return y_value
        points.append((x_value, y_value))
    if len(points) < min_count:
        return _failure(SketchAddPolylineError("INVALID_ARGUMENT", f"{field} requires at least {min_count} points"))
    return tuple(points)


def _require_int_list(value: object, field: str) -> tuple[int, ...] | SketchAddPolylineFailure:
    if not isinstance(value, list) or not value:
        return _failure(SketchAddPolylineError("INVALID_ARGUMENT", f"{field} must be a nonempty list of integers"))
    indices: list[int] = []
    for item in value:
        parsed = _require_int(item, field)
        if isinstance(parsed, dict):
            return parsed
        indices.append(parsed)
    return tuple(indices)


def _require_optional_floats(value: object, field: str) -> tuple[float, ...] | None | SketchAddPolylineFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchAddPolylineError("INVALID_ARGUMENT", f"{field} must be a list of numbers"))
    numbers: list[float] = []
    for item in value:
        parsed = _require_float(item, field)
        if isinstance(parsed, dict):
            return parsed
        numbers.append(parsed)
    return tuple(numbers)


def _require_optional_ints(value: object, field: str) -> tuple[int, ...] | None | SketchAddPolylineFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchAddPolylineError("INVALID_ARGUMENT", f"{field} must be a list of integers"))
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
        raise SketchAddPolylineError("SKETCH_NOT_FOUND", f"Sketch not found: {sketch_name!r}")
    if not _is_sketch(sketch):
        raise SketchAddPolylineError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {sketch_name!r}")
    return sketch

def build_sketch_add_polyline_request(doc_name: object, sketch_name: object, points: object, closed: object, construction: object) -> SketchAddPolylineRequest | SketchAddPolylineFailure:
    doc_name_value = _require_name(doc_name, 'doc_name')
    if isinstance(doc_name_value, dict):
        return doc_name_value
    sketch_name_value = _require_name(sketch_name, 'sketch_name')
    if isinstance(sketch_name_value, dict):
        return sketch_name_value
    points_value = _require_points(points, 'polyline', min_count=2)
    if isinstance(points_value, dict):
        return points_value
    closed_value = _require_bool(closed, 'closed', default=False)
    if isinstance(closed_value, dict):
        return closed_value
    construction_value = _require_bool(construction, 'construction', default=False)
    if isinstance(construction_value, dict):
        return construction_value
    return SketchAddPolylineRequest(
        doc_name=DocumentName(doc_name_value),
        sketch_name=SketchName(sketch_name_value),
        points=points_value,
        closed=closed_value,
        construction=construction_value,
    )

def apply_sketch_add_polyline(
    doc: SketchDocument,
    request: SketchAddPolylineRequest,
    collaborators: SketchAddPolylineCollaborators,
) -> SketchExecReceipt:
    """Mutate the sketch without recomputing or managing a transaction."""

    sketch = _require_sketch(doc, request.sketch_name)
    before_geo = sketch.GeometryCount
    before_con = sketch.ConstraintCount
    pts = list(request.points)
    if request.closed and pts[-1] != pts[0]:
        pts.append(pts[0])
    last = -1
    for index in range(len(pts) - 1):
        x1, y1 = pts[index]
        x2, y2 = pts[index + 1]
        last = int(
            sketch.addGeometry(
                collaborators.part.LineSegment(
                    collaborators.freecad.Vector(x1, y1, 0.0),
                    collaborators.freecad.Vector(x2, y2, 0.0),
                ),
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

def read_sketch_add_polyline_result(doc: SketchReadDocument, receipt: SketchExecReceipt) -> SketchExecInspection:
    sketch = doc.getObject(receipt.name)
    if sketch is None:
        raise SketchAddPolylineError("SKETCH_MISSING", f"Sketch is missing: {receipt.name!r}")
    if sketch is not receipt.sketch:
        raise SketchAddPolylineError("SKETCH_REPLACED", f"Sketch was replaced before commit: {receipt.name!r}")
    if not _is_sketch(sketch):
        raise SketchAddPolylineError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {receipt.name!r}")
    if sketch.GeometryCount <= receipt.geometry_count_before:
        raise SketchAddPolylineError(
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
class _SketchAddPolylineExecution:
    collaborators: SketchAddPolylineCollaborators
    request: SketchAddPolylineRequest
    created: SketchExecReceipt | None = None
    inspected: SketchExecInspection | None = None

    def apply(self, doc: SketchDocument) -> None:
        self.created = apply_sketch_add_polyline(doc, self.request, self.collaborators)

    def inspect(self, doc: SketchReadDocument) -> None:
        if self.created is None:
            raise SketchAddPolylineError(
                "INVALID_SKETCH_ADD_POLYLINE_RESULT",
                "sketch_add_polyline did not return an identity receipt",
            )
        self.inspected = read_sketch_add_polyline_result(doc, self.created)

    def run(self) -> SketchAddPolylineResult:
        result = run_sketch_add_polyline_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_add_polyline_uncertain(
                "SKETCH_ADD_POLYLINE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected sketch_add_polyline result",
                committed=True,
            )
        return make_sketch_add_polyline_success(SketchName(self.inspected.sketch_name), self.inspected.geometry_indices)


def run_sketch_add_polyline(
    collaborators: SketchAddPolylineCollaborators,
    doc_name: object, sketch_name: object, points: object, closed: object, construction: object,
) -> SketchAddPolylineResult:
    request = build_sketch_add_polyline_request(doc_name, sketch_name, points, closed, construction)
    if isinstance(request, dict):
        return request
    return _SketchAddPolylineExecution(collaborators, request).run()


class _SketchAddPolylineRpcFacade(Protocol):
    _cad_collaborators: SketchAddPolylineCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sketch_add_polyline(
    self: _SketchAddPolylineRpcFacade, doc_name: str, sketch_name: str, points: list[dict[str, float]], closed: bool = False, construction: bool = False,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_add_polyline(collaborators, doc_name, sketch_name, points, closed, construction)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_add_polyline", rpc_sketch_add_polyline)


__all__ = [
    "SketchAddPolylineCollaborators",
    "SketchAddPolylineError",
    "apply_sketch_add_polyline",
    "build_sketch_add_polyline_request",
    "read_sketch_add_polyline_result",
    "rpc_sketch_add_polyline",
    "run_sketch_add_polyline",
    "TYPED_RPC_HANDLER",
]
