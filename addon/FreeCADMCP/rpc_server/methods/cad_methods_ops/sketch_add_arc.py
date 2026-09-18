"""Typed ``sketch_add_arc`` mutation."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

try:
    from ...._shared.protocol.sketch_add_arc_contract import (
        SketchAddArcCollaborators,
        SketchAddArcFailure,
        SketchAddArcRequest,
        SketchAddArcResult,
        DocumentName,
        SketchDocument,
        SketchName,
        SketchObject,
        SketchReadDocument,
        make_sketch_add_arc_failure,
        make_sketch_add_arc_success,
        make_sketch_add_arc_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.sketch_add_arc_contract import (
        SketchAddArcCollaborators,
        SketchAddArcFailure,
        SketchAddArcRequest,
        SketchAddArcResult,
        DocumentName,
        SketchDocument,
        SketchName,
        SketchObject,
        SketchReadDocument,
        make_sketch_add_arc_failure,
        make_sketch_add_arc_success,
        make_sketch_add_arc_uncertain,
    )
from .sketch_add_arc_mutation import SketchAddArcError, run_sketch_add_arc_native_mutation


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


def _failure(error: SketchAddArcError, *, retry_safe: bool = True) -> SketchAddArcFailure:
    return make_sketch_add_arc_failure(error.code, str(error), retry_safe=retry_safe)


def _require_name(value: object, field: str) -> str | SketchAddArcFailure:
    if not isinstance(value, str) or not value.strip():
        return _failure(SketchAddArcError("INVALID_ARGUMENT", f"{field} must be a nonempty string"))
    return value


def _require_float(value: object, field: str) -> float | SketchAddArcFailure:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _failure(SketchAddArcError("INVALID_ARGUMENT", f"{field} must be a number"))
    return float(value)


def _require_int(value: object, field: str) -> int | SketchAddArcFailure:
    if type(value) is not int:
        return _failure(SketchAddArcError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_bool(value: object, field: str, *, default: bool) -> bool | SketchAddArcFailure:
    if value is None:
        return default
    if type(value) is not bool:
        return _failure(SketchAddArcError("INVALID_ARGUMENT", f"{field} must be a boolean"))
    return value


def _require_optional_int(value: object, field: str) -> int | None | SketchAddArcFailure:
    if value is None:
        return None
    if type(value) is not int:
        return _failure(SketchAddArcError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_optional_str(value: object, field: str) -> str | None | SketchAddArcFailure:
    if value is None:
        return None
    if not isinstance(value, str):
        return _failure(SketchAddArcError("INVALID_ARGUMENT", f"{field} must be a string"))
    return value


def _require_points(
    value: object, field: str, *, min_count: int
) -> tuple[tuple[float, float], ...] | SketchAddArcFailure:
    if not isinstance(value, list):
        return _failure(SketchAddArcError("INVALID_ARGUMENT", f"{field} must be a list of points"))
    points: list[tuple[float, float]] = []
    for item in value:
        if not isinstance(item, dict):
            return _failure(SketchAddArcError("INVALID_ARGUMENT", f"{field} entries must be objects"))
        x_value = _require_float(item.get("x"), f"{field}.x")
        y_value = _require_float(item.get("y"), f"{field}.y")
        if isinstance(x_value, dict):
            return x_value
        if isinstance(y_value, dict):
            return y_value
        points.append((x_value, y_value))
    if len(points) < min_count:
        return _failure(SketchAddArcError("INVALID_ARGUMENT", f"{field} requires at least {min_count} points"))
    return tuple(points)


def _require_int_list(value: object, field: str) -> tuple[int, ...] | SketchAddArcFailure:
    if not isinstance(value, list) or not value:
        return _failure(SketchAddArcError("INVALID_ARGUMENT", f"{field} must be a nonempty list of integers"))
    indices: list[int] = []
    for item in value:
        parsed = _require_int(item, field)
        if isinstance(parsed, dict):
            return parsed
        indices.append(parsed)
    return tuple(indices)


def _require_optional_floats(value: object, field: str) -> tuple[float, ...] | None | SketchAddArcFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchAddArcError("INVALID_ARGUMENT", f"{field} must be a list of numbers"))
    numbers: list[float] = []
    for item in value:
        parsed = _require_float(item, field)
        if isinstance(parsed, dict):
            return parsed
        numbers.append(parsed)
    return tuple(numbers)


def _require_optional_ints(value: object, field: str) -> tuple[int, ...] | None | SketchAddArcFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchAddArcError("INVALID_ARGUMENT", f"{field} must be a list of integers"))
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
        raise SketchAddArcError("SKETCH_NOT_FOUND", f"Sketch not found: {sketch_name!r}")
    if not _is_sketch(sketch):
        raise SketchAddArcError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {sketch_name!r}")
    return sketch

def build_sketch_add_arc_request(doc_name: object, sketch_name: object, cx: object, cy: object, radius: object, start_angle: object, end_angle: object, construction: object) -> SketchAddArcRequest | SketchAddArcFailure:
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
    start_angle_value = _require_float(start_angle, 'start_angle')
    if isinstance(start_angle_value, dict):
        return start_angle_value
    end_angle_value = _require_float(end_angle, 'end_angle')
    if isinstance(end_angle_value, dict):
        return end_angle_value
    construction_value = _require_bool(construction, 'construction', default=False)
    if isinstance(construction_value, dict):
        return construction_value
    return SketchAddArcRequest(
        doc_name=DocumentName(doc_name_value),
        sketch_name=SketchName(sketch_name_value),
        cx=cx_value,
        cy=cy_value,
        radius=radius_value,
        start_angle=start_angle_value,
        end_angle=end_angle_value,
        construction=construction_value,
    )

def apply_sketch_add_arc(
    doc: SketchDocument,
    request: SketchAddArcRequest,
    collaborators: SketchAddArcCollaborators,
) -> SketchExecReceipt:
    """Mutate the sketch without recomputing or managing a transaction."""

    sketch = _require_sketch(doc, request.sketch_name)
    before_geo = sketch.GeometryCount
    before_con = sketch.ConstraintCount
    center = collaborators.freecad.Vector(request.cx, request.cy, 0.0)
    normal = collaborators.freecad.Vector(0.0, 0.0, 1.0)
    circle = collaborators.part.Circle(center, normal, request.radius)
    idx = sketch.addGeometry(
        collaborators.part.ArcOfCircle(
            circle, math.radians(request.start_angle), math.radians(request.end_angle)
        ),
        request.construction,
    )
    return SketchExecReceipt(
        name=sketch.Name,
        sketch=sketch,
        geometry_index=int(idx),
        geometry_count_before=before_geo,
        constraint_count_before=before_con,
        sample_count=0,
    )

def read_sketch_add_arc_result(doc: SketchReadDocument, receipt: SketchExecReceipt) -> SketchExecInspection:
    sketch = doc.getObject(receipt.name)
    if sketch is None:
        raise SketchAddArcError("SKETCH_MISSING", f"Sketch is missing: {receipt.name!r}")
    if sketch is not receipt.sketch:
        raise SketchAddArcError("SKETCH_REPLACED", f"Sketch was replaced before commit: {receipt.name!r}")
    if not _is_sketch(sketch):
        raise SketchAddArcError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {receipt.name!r}")
    if sketch.GeometryCount <= receipt.geometry_count_before:
        raise SketchAddArcError(
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
class _SketchAddArcExecution:
    collaborators: SketchAddArcCollaborators
    request: SketchAddArcRequest
    created: SketchExecReceipt | None = None
    inspected: SketchExecInspection | None = None

    def apply(self, doc: SketchDocument) -> None:
        self.created = apply_sketch_add_arc(doc, self.request, self.collaborators)

    def inspect(self, doc: SketchReadDocument) -> None:
        if self.created is None:
            raise SketchAddArcError(
                "INVALID_SKETCH_ADD_ARC_RESULT",
                "sketch_add_arc did not return an identity receipt",
            )
        self.inspected = read_sketch_add_arc_result(doc, self.created)

    def run(self) -> SketchAddArcResult:
        result = run_sketch_add_arc_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_add_arc_uncertain(
                "SKETCH_ADD_ARC_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected sketch_add_arc result",
                committed=True,
            )
        return make_sketch_add_arc_success(SketchName(self.inspected.sketch_name), self.inspected.geometry_index)


def run_sketch_add_arc(
    collaborators: SketchAddArcCollaborators,
    doc_name: object, sketch_name: object, cx: object, cy: object, radius: object, start_angle: object, end_angle: object, construction: object,
) -> SketchAddArcResult:
    request = build_sketch_add_arc_request(doc_name, sketch_name, cx, cy, radius, start_angle, end_angle, construction)
    if isinstance(request, dict):
        return request
    return _SketchAddArcExecution(collaborators, request).run()


class _SketchAddArcRpcFacade(Protocol):
    _cad_collaborators: SketchAddArcCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sketch_add_arc(
    self: _SketchAddArcRpcFacade, doc_name: str, sketch_name: str, cx: float, cy: float, radius: float, start_angle: float, end_angle: float, construction: bool = False,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_add_arc(collaborators, doc_name, sketch_name, cx, cy, radius, start_angle, end_angle, construction)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_add_arc", rpc_sketch_add_arc)


__all__ = [
    "SketchAddArcCollaborators",
    "SketchAddArcError",
    "apply_sketch_add_arc",
    "build_sketch_add_arc_request",
    "read_sketch_add_arc_result",
    "rpc_sketch_add_arc",
    "run_sketch_add_arc",
    "TYPED_RPC_HANDLER",
]
