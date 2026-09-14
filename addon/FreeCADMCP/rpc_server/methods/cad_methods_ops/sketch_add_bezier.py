"""Typed ``sketch_add_bezier`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.sketch_add_bezier_contract import (
    SketchAddBezierCollaborators,
    SketchAddBezierFailure,
    SketchAddBezierRequest,
    SketchAddBezierResult,
    DocumentName,
    SketchDocument,
    SketchName,
    SketchObject,
    SketchReadDocument,
    make_sketch_add_bezier_failure,
    make_sketch_add_bezier_success,
    make_sketch_add_bezier_uncertain,
)
from .sketch_add_bezier_mutation import SketchAddBezierError, run_sketch_add_bezier_native_mutation


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


def _failure(error: SketchAddBezierError, *, retry_safe: bool = True) -> SketchAddBezierFailure:
    return make_sketch_add_bezier_failure(error.code, str(error), retry_safe=retry_safe)


def _require_name(value: object, field: str) -> str | SketchAddBezierFailure:
    if not isinstance(value, str) or not value.strip():
        return _failure(SketchAddBezierError("INVALID_ARGUMENT", f"{field} must be a nonempty string"))
    return value


def _require_float(value: object, field: str) -> float | SketchAddBezierFailure:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _failure(SketchAddBezierError("INVALID_ARGUMENT", f"{field} must be a number"))
    return float(value)


def _require_int(value: object, field: str) -> int | SketchAddBezierFailure:
    if type(value) is not int:
        return _failure(SketchAddBezierError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_bool(value: object, field: str, *, default: bool) -> bool | SketchAddBezierFailure:
    if value is None:
        return default
    if type(value) is not bool:
        return _failure(SketchAddBezierError("INVALID_ARGUMENT", f"{field} must be a boolean"))
    return value


def _require_optional_int(value: object, field: str) -> int | None | SketchAddBezierFailure:
    if value is None:
        return None
    if type(value) is not int:
        return _failure(SketchAddBezierError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_optional_str(value: object, field: str) -> str | None | SketchAddBezierFailure:
    if value is None:
        return None
    if not isinstance(value, str):
        return _failure(SketchAddBezierError("INVALID_ARGUMENT", f"{field} must be a string"))
    return value


def _require_points(
    value: object, field: str, *, min_count: int
) -> tuple[tuple[float, float], ...] | SketchAddBezierFailure:
    if not isinstance(value, list):
        return _failure(SketchAddBezierError("INVALID_ARGUMENT", f"{field} must be a list of points"))
    points: list[tuple[float, float]] = []
    for item in value:
        if not isinstance(item, dict):
            return _failure(SketchAddBezierError("INVALID_ARGUMENT", f"{field} entries must be objects"))
        x_value = _require_float(item.get("x"), f"{field}.x")
        y_value = _require_float(item.get("y"), f"{field}.y")
        if isinstance(x_value, dict):
            return x_value
        if isinstance(y_value, dict):
            return y_value
        points.append((x_value, y_value))
    if len(points) < min_count:
        return _failure(SketchAddBezierError("INVALID_ARGUMENT", f"{field} requires at least {min_count} points"))
    return tuple(points)


def _require_int_list(value: object, field: str) -> tuple[int, ...] | SketchAddBezierFailure:
    if not isinstance(value, list) or not value:
        return _failure(SketchAddBezierError("INVALID_ARGUMENT", f"{field} must be a nonempty list of integers"))
    indices: list[int] = []
    for item in value:
        parsed = _require_int(item, field)
        if isinstance(parsed, dict):
            return parsed
        indices.append(parsed)
    return tuple(indices)


def _require_optional_floats(value: object, field: str) -> tuple[float, ...] | None | SketchAddBezierFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchAddBezierError("INVALID_ARGUMENT", f"{field} must be a list of numbers"))
    numbers: list[float] = []
    for item in value:
        parsed = _require_float(item, field)
        if isinstance(parsed, dict):
            return parsed
        numbers.append(parsed)
    return tuple(numbers)


def _require_optional_ints(value: object, field: str) -> tuple[int, ...] | None | SketchAddBezierFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchAddBezierError("INVALID_ARGUMENT", f"{field} must be a list of integers"))
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
        raise SketchAddBezierError("SKETCH_NOT_FOUND", f"Sketch not found: {sketch_name!r}")
    if not _is_sketch(sketch):
        raise SketchAddBezierError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {sketch_name!r}")
    return sketch

def build_sketch_add_bezier_request(doc_name: object, sketch_name: object, poles: object, construction: object) -> SketchAddBezierRequest | SketchAddBezierFailure:
    doc_name_value = _require_name(doc_name, 'doc_name')
    if isinstance(doc_name_value, dict):
        return doc_name_value
    sketch_name_value = _require_name(sketch_name, 'sketch_name')
    if isinstance(sketch_name_value, dict):
        return sketch_name_value
    poles_value = _require_points(poles, 'poles', min_count=2)
    if isinstance(poles_value, dict):
        return poles_value
    construction_value = _require_bool(construction, 'construction', default=False)
    if isinstance(construction_value, dict):
        return construction_value
    return SketchAddBezierRequest(
        doc_name=DocumentName(doc_name_value),
        sketch_name=SketchName(sketch_name_value),
        poles=poles_value,
        construction=construction_value,
    )

def apply_sketch_add_bezier(
    doc: SketchDocument,
    request: SketchAddBezierRequest,
    collaborators: SketchAddBezierCollaborators,
) -> SketchExecReceipt:
    """Mutate the sketch without recomputing or managing a transaction."""

    sketch = _require_sketch(doc, request.sketch_name)
    if len(request.poles) < 2:
        raise SketchAddBezierError("INVALID_ARGUMENT", "poles requires at least 2 points")
    before_geo = sketch.GeometryCount
    before_con = sketch.ConstraintCount
    poles = [
        collaborators.freecad.Vector(x, y, 0.0) for x, y in request.poles
    ]
    curve = collaborators.part.BezierCurve()
    curve.setPoles(poles)
    idx = sketch.addGeometry(curve, request.construction)
    return SketchExecReceipt(
        name=sketch.Name,
        sketch=sketch,
        geometry_index=int(idx),
        geometry_count_before=before_geo,
        constraint_count_before=before_con,
        sample_count=0,
    )

def read_sketch_add_bezier_result(doc: SketchReadDocument, receipt: SketchExecReceipt) -> SketchExecInspection:
    sketch = doc.getObject(receipt.name)
    if sketch is None:
        raise SketchAddBezierError("SKETCH_MISSING", f"Sketch is missing: {receipt.name!r}")
    if sketch is not receipt.sketch:
        raise SketchAddBezierError("SKETCH_REPLACED", f"Sketch was replaced before commit: {receipt.name!r}")
    if not _is_sketch(sketch):
        raise SketchAddBezierError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {receipt.name!r}")
    if sketch.GeometryCount <= receipt.geometry_count_before:
        raise SketchAddBezierError(
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
class _SketchAddBezierExecution:
    collaborators: SketchAddBezierCollaborators
    request: SketchAddBezierRequest
    created: SketchExecReceipt | None = None
    inspected: SketchExecInspection | None = None

    def apply(self, doc: SketchDocument) -> None:
        self.created = apply_sketch_add_bezier(doc, self.request, self.collaborators)

    def inspect(self, doc: SketchReadDocument) -> None:
        if self.created is None:
            raise SketchAddBezierError(
                "INVALID_SKETCH_ADD_BEZIER_RESULT",
                "sketch_add_bezier did not return an identity receipt",
            )
        self.inspected = read_sketch_add_bezier_result(doc, self.created)

    def run(self) -> SketchAddBezierResult:
        result = run_sketch_add_bezier_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_add_bezier_uncertain(
                "SKETCH_ADD_BEZIER_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected sketch_add_bezier result",
                committed=True,
            )
        return make_sketch_add_bezier_success(SketchName(self.inspected.sketch_name), self.inspected.geometry_index)


def run_sketch_add_bezier(
    collaborators: SketchAddBezierCollaborators,
    doc_name: object, sketch_name: object, poles: object, construction: object,
) -> SketchAddBezierResult:
    request = build_sketch_add_bezier_request(doc_name, sketch_name, poles, construction)
    if isinstance(request, dict):
        return request
    return _SketchAddBezierExecution(collaborators, request).run()


class _SketchAddBezierRpcFacade(Protocol):
    _cad_collaborators: SketchAddBezierCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sketch_add_bezier(
    self: _SketchAddBezierRpcFacade, doc_name: str, sketch_name: str, poles: list[dict[str, float]], construction: bool = False,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_add_bezier(collaborators, doc_name, sketch_name, poles, construction)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_add_bezier", rpc_sketch_add_bezier)


__all__ = [
    "SketchAddBezierCollaborators",
    "SketchAddBezierError",
    "apply_sketch_add_bezier",
    "build_sketch_add_bezier_request",
    "read_sketch_add_bezier_result",
    "rpc_sketch_add_bezier",
    "run_sketch_add_bezier",
    "TYPED_RPC_HANDLER",
]
