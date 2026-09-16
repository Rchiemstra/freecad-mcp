"""Typed ``sketch_add_circle`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.sketch_add_circle_contract import (
    SketchAddCircleCollaborators,
    SketchAddCircleFailure,
    SketchAddCircleRequest,
    SketchAddCircleResult,
    DocumentName,
    SketchDocument,
    SketchName,
    SketchObject,
    SketchReadDocument,
    make_sketch_add_circle_failure,
    make_sketch_add_circle_success,
    make_sketch_add_circle_uncertain,
)
from .sketch_add_circle_mutation import SketchAddCircleError, run_sketch_add_circle_native_mutation


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


def _failure(error: SketchAddCircleError, *, retry_safe: bool = True) -> SketchAddCircleFailure:
    return make_sketch_add_circle_failure(error.code, str(error), retry_safe=retry_safe)


def _require_name(value: object, field: str) -> str | SketchAddCircleFailure:
    if not isinstance(value, str) or not value.strip():
        return _failure(SketchAddCircleError("INVALID_ARGUMENT", f"{field} must be a nonempty string"))
    return value


def _require_float(value: object, field: str) -> float | SketchAddCircleFailure:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _failure(SketchAddCircleError("INVALID_ARGUMENT", f"{field} must be a number"))
    return float(value)


def _require_int(value: object, field: str) -> int | SketchAddCircleFailure:
    if type(value) is not int:
        return _failure(SketchAddCircleError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_bool(value: object, field: str, *, default: bool) -> bool | SketchAddCircleFailure:
    if value is None:
        return default
    if type(value) is not bool:
        return _failure(SketchAddCircleError("INVALID_ARGUMENT", f"{field} must be a boolean"))
    return value


def _require_optional_int(value: object, field: str) -> int | None | SketchAddCircleFailure:
    if value is None:
        return None
    if type(value) is not int:
        return _failure(SketchAddCircleError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_optional_str(value: object, field: str) -> str | None | SketchAddCircleFailure:
    if value is None:
        return None
    if not isinstance(value, str):
        return _failure(SketchAddCircleError("INVALID_ARGUMENT", f"{field} must be a string"))
    return value


def _require_points(
    value: object, field: str, *, min_count: int
) -> tuple[tuple[float, float], ...] | SketchAddCircleFailure:
    if not isinstance(value, list):
        return _failure(SketchAddCircleError("INVALID_ARGUMENT", f"{field} must be a list of points"))
    points: list[tuple[float, float]] = []
    for item in value:
        if not isinstance(item, dict):
            return _failure(SketchAddCircleError("INVALID_ARGUMENT", f"{field} entries must be objects"))
        x_value = _require_float(item.get("x"), f"{field}.x")
        y_value = _require_float(item.get("y"), f"{field}.y")
        if isinstance(x_value, dict):
            return x_value
        if isinstance(y_value, dict):
            return y_value
        points.append((x_value, y_value))
    if len(points) < min_count:
        return _failure(SketchAddCircleError("INVALID_ARGUMENT", f"{field} requires at least {min_count} points"))
    return tuple(points)


def _require_int_list(value: object, field: str) -> tuple[int, ...] | SketchAddCircleFailure:
    if not isinstance(value, list) or not value:
        return _failure(SketchAddCircleError("INVALID_ARGUMENT", f"{field} must be a nonempty list of integers"))
    indices: list[int] = []
    for item in value:
        parsed = _require_int(item, field)
        if isinstance(parsed, dict):
            return parsed
        indices.append(parsed)
    return tuple(indices)


def _require_optional_floats(value: object, field: str) -> tuple[float, ...] | None | SketchAddCircleFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchAddCircleError("INVALID_ARGUMENT", f"{field} must be a list of numbers"))
    numbers: list[float] = []
    for item in value:
        parsed = _require_float(item, field)
        if isinstance(parsed, dict):
            return parsed
        numbers.append(parsed)
    return tuple(numbers)


def _require_optional_ints(value: object, field: str) -> tuple[int, ...] | None | SketchAddCircleFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchAddCircleError("INVALID_ARGUMENT", f"{field} must be a list of integers"))
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
        raise SketchAddCircleError("SKETCH_NOT_FOUND", f"Sketch not found: {sketch_name!r}")
    if not _is_sketch(sketch):
        raise SketchAddCircleError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {sketch_name!r}")
    return sketch

def build_sketch_add_circle_request(doc_name: object, sketch_name: object, cx: object, cy: object, radius: object, construction: object) -> SketchAddCircleRequest | SketchAddCircleFailure:
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
    construction_value = _require_bool(construction, 'construction', default=False)
    if isinstance(construction_value, dict):
        return construction_value
    return SketchAddCircleRequest(
        doc_name=DocumentName(doc_name_value),
        sketch_name=SketchName(sketch_name_value),
        cx=cx_value,
        cy=cy_value,
        radius=radius_value,
        construction=construction_value,
    )

def apply_sketch_add_circle(
    doc: SketchDocument,
    request: SketchAddCircleRequest,
    collaborators: SketchAddCircleCollaborators,
) -> SketchExecReceipt:
    """Mutate the sketch without recomputing or managing a transaction."""

    sketch = _require_sketch(doc, request.sketch_name)
    before_geo = sketch.GeometryCount
    before_con = sketch.ConstraintCount
    center = collaborators.freecad.Vector(request.cx, request.cy, 0.0)
    normal = collaborators.freecad.Vector(0.0, 0.0, 1.0)
    idx = sketch.addGeometry(
        collaborators.part.Circle(center, normal, request.radius), request.construction
    )
    return SketchExecReceipt(
        name=sketch.Name,
        sketch=sketch,
        geometry_index=int(idx),
        geometry_count_before=before_geo,
        constraint_count_before=before_con,
        sample_count=0,
    )

def read_sketch_add_circle_result(doc: SketchReadDocument, receipt: SketchExecReceipt) -> SketchExecInspection:
    sketch = doc.getObject(receipt.name)
    if sketch is None:
        raise SketchAddCircleError("SKETCH_MISSING", f"Sketch is missing: {receipt.name!r}")
    if sketch is not receipt.sketch:
        raise SketchAddCircleError("SKETCH_REPLACED", f"Sketch was replaced before commit: {receipt.name!r}")
    if not _is_sketch(sketch):
        raise SketchAddCircleError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {receipt.name!r}")
    if sketch.GeometryCount <= receipt.geometry_count_before:
        raise SketchAddCircleError(
            "GEOMETRY_MISSING",
            f"Created sketch geometry is missing: {receipt.name!r}",
        )
    return SketchExecInspection(
        sketch_name=SketchName(receipt.name),
        geometry_index=receipt.geometry_index,
        geometry_indices=[receipt.geometry_index] if receipt.geometry_index >= 0 else [],
        constraint_index=receipt.geometry_index,
        sample_count=receipt.sample_count,
    )


@dataclass(slots=True)
class _SketchAddCircleExecution:
    collaborators: SketchAddCircleCollaborators
    request: SketchAddCircleRequest
    created: SketchExecReceipt | None = None
    inspected: SketchExecInspection | None = None

    def apply(self, doc: SketchDocument) -> None:
        self.created = apply_sketch_add_circle(doc, self.request, self.collaborators)

    def inspect(self, doc: SketchReadDocument) -> None:
        if self.created is None:
            raise SketchAddCircleError(
                "INVALID_SKETCH_ADD_CIRCLE_RESULT",
                "sketch_add_circle did not return an identity receipt",
            )
        self.inspected = read_sketch_add_circle_result(doc, self.created)

    def run(self) -> SketchAddCircleResult:
        result = run_sketch_add_circle_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_add_circle_uncertain(
                "SKETCH_ADD_CIRCLE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected sketch_add_circle result",
                committed=True,
            )
        return make_sketch_add_circle_success(SketchName(self.inspected.sketch_name), self.inspected.geometry_index)


def run_sketch_add_circle(
    collaborators: SketchAddCircleCollaborators,
    doc_name: object, sketch_name: object, cx: object, cy: object, radius: object, construction: object,
) -> SketchAddCircleResult:
    request = build_sketch_add_circle_request(doc_name, sketch_name, cx, cy, radius, construction)
    if isinstance(request, dict):
        return request
    return _SketchAddCircleExecution(collaborators, request).run()


class _SketchAddCircleRpcFacade(Protocol):
    _cad_collaborators: SketchAddCircleCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sketch_add_circle(
    self: _SketchAddCircleRpcFacade, doc_name: str, sketch_name: str, cx: float, cy: float, radius: float, construction: bool = False,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_add_circle(collaborators, doc_name, sketch_name, cx, cy, radius, construction)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_add_circle", rpc_sketch_add_circle)


__all__ = [
    "SketchAddCircleCollaborators",
    "SketchAddCircleError",
    "apply_sketch_add_circle",
    "build_sketch_add_circle_request",
    "read_sketch_add_circle_result",
    "rpc_sketch_add_circle",
    "run_sketch_add_circle",
    "TYPED_RPC_HANDLER",
]
