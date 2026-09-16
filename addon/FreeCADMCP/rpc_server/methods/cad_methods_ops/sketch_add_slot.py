"""Typed ``sketch_add_slot`` mutation."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.sketch_add_slot_contract import (
    SketchAddSlotCollaborators,
    SketchAddSlotFailure,
    SketchAddSlotRequest,
    SketchAddSlotResult,
    DocumentName,
    SketchDocument,
    SketchName,
    SketchObject,
    SketchReadDocument,
    make_sketch_add_slot_failure,
    make_sketch_add_slot_success,
    make_sketch_add_slot_uncertain,
)
from .sketch_add_slot_mutation import SketchAddSlotError, run_sketch_add_slot_native_mutation


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


def _failure(error: SketchAddSlotError, *, retry_safe: bool = True) -> SketchAddSlotFailure:
    return make_sketch_add_slot_failure(error.code, str(error), retry_safe=retry_safe)


def _require_name(value: object, field: str) -> str | SketchAddSlotFailure:
    if not isinstance(value, str) or not value.strip():
        return _failure(SketchAddSlotError("INVALID_ARGUMENT", f"{field} must be a nonempty string"))
    return value


def _require_float(value: object, field: str) -> float | SketchAddSlotFailure:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _failure(SketchAddSlotError("INVALID_ARGUMENT", f"{field} must be a number"))
    return float(value)


def _require_int(value: object, field: str) -> int | SketchAddSlotFailure:
    if type(value) is not int:
        return _failure(SketchAddSlotError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_bool(value: object, field: str, *, default: bool) -> bool | SketchAddSlotFailure:
    if value is None:
        return default
    if type(value) is not bool:
        return _failure(SketchAddSlotError("INVALID_ARGUMENT", f"{field} must be a boolean"))
    return value


def _require_optional_int(value: object, field: str) -> int | None | SketchAddSlotFailure:
    if value is None:
        return None
    if type(value) is not int:
        return _failure(SketchAddSlotError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_optional_str(value: object, field: str) -> str | None | SketchAddSlotFailure:
    if value is None:
        return None
    if not isinstance(value, str):
        return _failure(SketchAddSlotError("INVALID_ARGUMENT", f"{field} must be a string"))
    return value


def _require_points(
    value: object, field: str, *, min_count: int
) -> tuple[tuple[float, float], ...] | SketchAddSlotFailure:
    if not isinstance(value, list):
        return _failure(SketchAddSlotError("INVALID_ARGUMENT", f"{field} must be a list of points"))
    points: list[tuple[float, float]] = []
    for item in value:
        if not isinstance(item, dict):
            return _failure(SketchAddSlotError("INVALID_ARGUMENT", f"{field} entries must be objects"))
        x_value = _require_float(item.get("x"), f"{field}.x")
        y_value = _require_float(item.get("y"), f"{field}.y")
        if isinstance(x_value, dict):
            return x_value
        if isinstance(y_value, dict):
            return y_value
        points.append((x_value, y_value))
    if len(points) < min_count:
        return _failure(SketchAddSlotError("INVALID_ARGUMENT", f"{field} requires at least {min_count} points"))
    return tuple(points)


def _require_int_list(value: object, field: str) -> tuple[int, ...] | SketchAddSlotFailure:
    if not isinstance(value, list) or not value:
        return _failure(SketchAddSlotError("INVALID_ARGUMENT", f"{field} must be a nonempty list of integers"))
    indices: list[int] = []
    for item in value:
        parsed = _require_int(item, field)
        if isinstance(parsed, dict):
            return parsed
        indices.append(parsed)
    return tuple(indices)


def _require_optional_floats(value: object, field: str) -> tuple[float, ...] | None | SketchAddSlotFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchAddSlotError("INVALID_ARGUMENT", f"{field} must be a list of numbers"))
    numbers: list[float] = []
    for item in value:
        parsed = _require_float(item, field)
        if isinstance(parsed, dict):
            return parsed
        numbers.append(parsed)
    return tuple(numbers)


def _require_optional_ints(value: object, field: str) -> tuple[int, ...] | None | SketchAddSlotFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchAddSlotError("INVALID_ARGUMENT", f"{field} must be a list of integers"))
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
        raise SketchAddSlotError("SKETCH_NOT_FOUND", f"Sketch not found: {sketch_name!r}")
    if not _is_sketch(sketch):
        raise SketchAddSlotError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {sketch_name!r}")
    return sketch

def build_sketch_add_slot_request(doc_name: object, sketch_name: object, x1: object, y1: object, x2: object, y2: object, width: object, construction: object) -> SketchAddSlotRequest | SketchAddSlotFailure:
    doc_name_value = _require_name(doc_name, 'doc_name')
    if isinstance(doc_name_value, dict):
        return doc_name_value
    sketch_name_value = _require_name(sketch_name, 'sketch_name')
    if isinstance(sketch_name_value, dict):
        return sketch_name_value
    x1_value = _require_float(x1, 'x1')
    if isinstance(x1_value, dict):
        return x1_value
    y1_value = _require_float(y1, 'y1')
    if isinstance(y1_value, dict):
        return y1_value
    x2_value = _require_float(x2, 'x2')
    if isinstance(x2_value, dict):
        return x2_value
    y2_value = _require_float(y2, 'y2')
    if isinstance(y2_value, dict):
        return y2_value
    width_value = _require_float(width, 'width')
    if isinstance(width_value, dict):
        return width_value
    construction_value = _require_bool(construction, 'construction', default=False)
    if isinstance(construction_value, dict):
        return construction_value
    return SketchAddSlotRequest(
        doc_name=DocumentName(doc_name_value),
        sketch_name=SketchName(sketch_name_value),
        x1=x1_value,
        y1=y1_value,
        x2=x2_value,
        y2=y2_value,
        width=width_value,
        construction=construction_value,
    )

def apply_sketch_add_slot(
    doc: SketchDocument,
    request: SketchAddSlotRequest,
    collaborators: SketchAddSlotCollaborators,
) -> SketchExecReceipt:
    """Mutate the sketch without recomputing or managing a transaction."""

    sketch = _require_sketch(doc, request.sketch_name)
    before_geo = sketch.GeometryCount
    before_con = sketch.ConstraintCount
    dx = request.x2 - request.x1
    dy = request.y2 - request.y1
    length = math.hypot(dx, dy)
    if length < 1e-9:
        raise SketchAddSlotError("INVALID_ARGUMENT", "slot start and end are the same point")
    ux, uy = dx / length, dy / length
    px, py = -uy * request.width / 2.0, ux * request.width / 2.0
    radius = request.width / 2.0
    last = -1
    pairs = (
        (request.x1 + px, request.y1 + py, request.x2 + px, request.y2 + py),
        (request.x2 - px, request.y2 - py, request.x1 - px, request.y1 - py),
    )
    for x1, y1, x2, y2 in pairs:
        last = int(
            sketch.addGeometry(
                collaborators.part.LineSegment(
                    collaborators.freecad.Vector(x1, y1, 0.0),
                    collaborators.freecad.Vector(x2, y2, 0.0),
                ),
                request.construction,
            )
        )
    a1_l = math.atan2(uy, ux) + math.pi / 2.0
    a2_l = math.atan2(uy, ux) + 3.0 * math.pi / 2.0
    c1 = collaborators.part.Circle(
        collaborators.freecad.Vector(request.x1, request.y1, 0.0),
        collaborators.freecad.Vector(0.0, 0.0, 1.0),
        radius,
    )
    last = int(sketch.addGeometry(collaborators.part.ArcOfCircle(c1, a1_l, a2_l), request.construction))
    a1_r = math.atan2(uy, ux) - math.pi / 2.0
    a2_r = math.atan2(uy, ux) + math.pi / 2.0
    c2 = collaborators.part.Circle(
        collaborators.freecad.Vector(request.x2, request.y2, 0.0),
        collaborators.freecad.Vector(0.0, 0.0, 1.0),
        radius,
    )
    last = int(sketch.addGeometry(collaborators.part.ArcOfCircle(c2, a1_r, a2_r), request.construction))
    return SketchExecReceipt(
        name=sketch.Name,
        sketch=sketch,
        geometry_index=last,
        geometry_count_before=before_geo,
        constraint_count_before=before_con,
        sample_count=0,
    )

def read_sketch_add_slot_result(doc: SketchReadDocument, receipt: SketchExecReceipt) -> SketchExecInspection:
    sketch = doc.getObject(receipt.name)
    if sketch is None:
        raise SketchAddSlotError("SKETCH_MISSING", f"Sketch is missing: {receipt.name!r}")
    if sketch is not receipt.sketch:
        raise SketchAddSlotError("SKETCH_REPLACED", f"Sketch was replaced before commit: {receipt.name!r}")
    if not _is_sketch(sketch):
        raise SketchAddSlotError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {receipt.name!r}")
    if sketch.GeometryCount <= receipt.geometry_count_before:
        raise SketchAddSlotError(
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
class _SketchAddSlotExecution:
    collaborators: SketchAddSlotCollaborators
    request: SketchAddSlotRequest
    created: SketchExecReceipt | None = None
    inspected: SketchExecInspection | None = None

    def apply(self, doc: SketchDocument) -> None:
        self.created = apply_sketch_add_slot(doc, self.request, self.collaborators)

    def inspect(self, doc: SketchReadDocument) -> None:
        if self.created is None:
            raise SketchAddSlotError(
                "INVALID_SKETCH_ADD_SLOT_RESULT",
                "sketch_add_slot did not return an identity receipt",
            )
        self.inspected = read_sketch_add_slot_result(doc, self.created)

    def run(self) -> SketchAddSlotResult:
        result = run_sketch_add_slot_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_add_slot_uncertain(
                "SKETCH_ADD_SLOT_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected sketch_add_slot result",
                committed=True,
            )
        return make_sketch_add_slot_success(SketchName(self.inspected.sketch_name), self.inspected.geometry_indices)


def run_sketch_add_slot(
    collaborators: SketchAddSlotCollaborators,
    doc_name: object, sketch_name: object, x1: object, y1: object, x2: object, y2: object, width: object, construction: object,
) -> SketchAddSlotResult:
    request = build_sketch_add_slot_request(doc_name, sketch_name, x1, y1, x2, y2, width, construction)
    if isinstance(request, dict):
        return request
    return _SketchAddSlotExecution(collaborators, request).run()


class _SketchAddSlotRpcFacade(Protocol):
    _cad_collaborators: SketchAddSlotCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sketch_add_slot(
    self: _SketchAddSlotRpcFacade, doc_name: str, sketch_name: str, x1: float, y1: float, x2: float, y2: float, width: float, construction: bool = False,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_add_slot(collaborators, doc_name, sketch_name, x1, y1, x2, y2, width, construction)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_add_slot", rpc_sketch_add_slot)


__all__ = [
    "SketchAddSlotCollaborators",
    "SketchAddSlotError",
    "apply_sketch_add_slot",
    "build_sketch_add_slot_request",
    "read_sketch_add_slot_result",
    "rpc_sketch_add_slot",
    "run_sketch_add_slot",
    "TYPED_RPC_HANDLER",
]
