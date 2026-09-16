"""Typed ``sketch_add_parametric_curve`` mutation."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.sketch_add_parametric_curve_contract import (
    SketchAddParametricCurveCollaborators,
    SketchAddParametricCurveFailure,
    SketchAddParametricCurveRequest,
    SketchAddParametricCurveResult,
    DocumentName,
    SketchDocument,
    SketchName,
    SketchObject,
    SketchReadDocument,
    make_sketch_add_parametric_curve_failure,
    make_sketch_add_parametric_curve_success,
    make_sketch_add_parametric_curve_uncertain,
)
from .sketch_add_parametric_curve_mutation import SketchAddParametricCurveError, run_sketch_add_parametric_curve_native_mutation


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


def _failure(error: SketchAddParametricCurveError, *, retry_safe: bool = True) -> SketchAddParametricCurveFailure:
    return make_sketch_add_parametric_curve_failure(error.code, str(error), retry_safe=retry_safe)


def _require_name(value: object, field: str) -> str | SketchAddParametricCurveFailure:
    if not isinstance(value, str) or not value.strip():
        return _failure(SketchAddParametricCurveError("INVALID_ARGUMENT", f"{field} must be a nonempty string"))
    return value


def _require_float(value: object, field: str) -> float | SketchAddParametricCurveFailure:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _failure(SketchAddParametricCurveError("INVALID_ARGUMENT", f"{field} must be a number"))
    return float(value)


def _require_int(value: object, field: str) -> int | SketchAddParametricCurveFailure:
    if type(value) is not int:
        return _failure(SketchAddParametricCurveError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_bool(value: object, field: str, *, default: bool) -> bool | SketchAddParametricCurveFailure:
    if value is None:
        return default
    if type(value) is not bool:
        return _failure(SketchAddParametricCurveError("INVALID_ARGUMENT", f"{field} must be a boolean"))
    return value


def _require_optional_int(value: object, field: str) -> int | None | SketchAddParametricCurveFailure:
    if value is None:
        return None
    if type(value) is not int:
        return _failure(SketchAddParametricCurveError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_optional_str(value: object, field: str) -> str | None | SketchAddParametricCurveFailure:
    if value is None:
        return None
    if not isinstance(value, str):
        return _failure(SketchAddParametricCurveError("INVALID_ARGUMENT", f"{field} must be a string"))
    return value


def _require_points(
    value: object, field: str, *, min_count: int
) -> tuple[tuple[float, float], ...] | SketchAddParametricCurveFailure:
    if not isinstance(value, list):
        return _failure(SketchAddParametricCurveError("INVALID_ARGUMENT", f"{field} must be a list of points"))
    points: list[tuple[float, float]] = []
    for item in value:
        if not isinstance(item, dict):
            return _failure(SketchAddParametricCurveError("INVALID_ARGUMENT", f"{field} entries must be objects"))
        x_value = _require_float(item.get("x"), f"{field}.x")
        y_value = _require_float(item.get("y"), f"{field}.y")
        if isinstance(x_value, dict):
            return x_value
        if isinstance(y_value, dict):
            return y_value
        points.append((x_value, y_value))
    if len(points) < min_count:
        return _failure(SketchAddParametricCurveError("INVALID_ARGUMENT", f"{field} requires at least {min_count} points"))
    return tuple(points)


def _require_int_list(value: object, field: str) -> tuple[int, ...] | SketchAddParametricCurveFailure:
    if not isinstance(value, list) or not value:
        return _failure(SketchAddParametricCurveError("INVALID_ARGUMENT", f"{field} must be a nonempty list of integers"))
    indices: list[int] = []
    for item in value:
        parsed = _require_int(item, field)
        if isinstance(parsed, dict):
            return parsed
        indices.append(parsed)
    return tuple(indices)


def _require_optional_floats(value: object, field: str) -> tuple[float, ...] | None | SketchAddParametricCurveFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchAddParametricCurveError("INVALID_ARGUMENT", f"{field} must be a list of numbers"))
    numbers: list[float] = []
    for item in value:
        parsed = _require_float(item, field)
        if isinstance(parsed, dict):
            return parsed
        numbers.append(parsed)
    return tuple(numbers)


def _require_optional_ints(value: object, field: str) -> tuple[int, ...] | None | SketchAddParametricCurveFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchAddParametricCurveError("INVALID_ARGUMENT", f"{field} must be a list of integers"))
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
        raise SketchAddParametricCurveError("SKETCH_NOT_FOUND", f"Sketch not found: {sketch_name!r}")
    if not _is_sketch(sketch):
        raise SketchAddParametricCurveError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {sketch_name!r}")
    return sketch

def build_sketch_add_parametric_curve_request(doc_name: object, sketch_name: object, x_expr: object, y_expr: object, t_start: object, t_end: object, samples: object, construction: object) -> SketchAddParametricCurveRequest | SketchAddParametricCurveFailure:
    doc_name_value = _require_name(doc_name, 'doc_name')
    if isinstance(doc_name_value, dict):
        return doc_name_value
    sketch_name_value = _require_name(sketch_name, 'sketch_name')
    if isinstance(sketch_name_value, dict):
        return sketch_name_value
    x_expr_value = _require_name(x_expr, 'x_expr')
    if isinstance(x_expr_value, dict):
        return x_expr_value
    y_expr_value = _require_name(y_expr, 'y_expr')
    if isinstance(y_expr_value, dict):
        return y_expr_value
    t_start_value = _require_float(t_start, 't_start')
    if isinstance(t_start_value, dict):
        return t_start_value
    t_end_value = _require_float(t_end, 't_end')
    if isinstance(t_end_value, dict):
        return t_end_value
    samples_value = _require_int(samples, 'samples')
    if isinstance(samples_value, dict):
        return samples_value
    construction_value = _require_bool(construction, 'construction', default=False)
    if isinstance(construction_value, dict):
        return construction_value
    if samples_value < 10 or samples_value > 2000:
        return _failure(SketchAddParametricCurveError("INVALID_ARGUMENT", "samples must be between 10 and 2000"))
    if t_start_value >= t_end_value:
        return _failure(SketchAddParametricCurveError("INVALID_ARGUMENT", "t_start must be less than t_end"))
    return SketchAddParametricCurveRequest(
        doc_name=DocumentName(doc_name_value),
        sketch_name=SketchName(sketch_name_value),
        x_expr=x_expr_value,
        y_expr=y_expr_value,
        t_start=t_start_value,
        t_end=t_end_value,
        samples=samples_value,
        construction=construction_value,
    )

def apply_sketch_add_parametric_curve(
    doc: SketchDocument,
    request: SketchAddParametricCurveRequest,
    collaborators: SketchAddParametricCurveCollaborators,
) -> SketchExecReceipt:
    """Mutate the sketch without recomputing or managing a transaction."""

    sketch = _require_sketch(doc, request.sketch_name)
    before_geo = sketch.GeometryCount
    before_con = sketch.ConstraintCount
    sample_pts = []
    for step in range(request.samples + 1):
        t = request.t_start + (request.t_end - request.t_start) * step / request.samples
        env = {"t": t, "math": math}
        x_val = eval(request.x_expr, {"__builtins__": {}}, env)
        y_val = eval(request.y_expr, {"__builtins__": {}}, env)
        if not isinstance(x_val, (int, float)) or not isinstance(y_val, (int, float)) or isinstance(x_val, bool) or isinstance(y_val, bool):
            raise SketchAddParametricCurveError("INVALID_ARGUMENT", "parametric expressions must evaluate to numbers")
        sample_pts.append(collaborators.freecad.Vector(float(x_val), float(y_val), 0.0))
    unique_pts = [sample_pts[0]]
    for point in sample_pts[1:]:
        if (point - unique_pts[-1]).Length > 1e-9:
            unique_pts.append(point)
    if len(unique_pts) < 2:
        raise SketchAddParametricCurveError("INVALID_ARGUMENT", "Parametric curve collapsed to a single point")
    curve = collaborators.part.BSplineCurve()
    curve.interpolate(unique_pts)
    idx = sketch.addGeometry(curve, request.construction)
    return SketchExecReceipt(
        name=sketch.Name,
        sketch=sketch,
        geometry_index=int(idx),
        geometry_count_before=before_geo,
        constraint_count_before=before_con,
        sample_count=len(unique_pts),
    )

def read_sketch_add_parametric_curve_result(doc: SketchReadDocument, receipt: SketchExecReceipt) -> SketchExecInspection:
    sketch = doc.getObject(receipt.name)
    if sketch is None:
        raise SketchAddParametricCurveError("SKETCH_MISSING", f"Sketch is missing: {receipt.name!r}")
    if sketch is not receipt.sketch:
        raise SketchAddParametricCurveError("SKETCH_REPLACED", f"Sketch was replaced before commit: {receipt.name!r}")
    if not _is_sketch(sketch):
        raise SketchAddParametricCurveError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {receipt.name!r}")
    if sketch.GeometryCount <= receipt.geometry_count_before:
        raise SketchAddParametricCurveError(
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
class _SketchAddParametricCurveExecution:
    collaborators: SketchAddParametricCurveCollaborators
    request: SketchAddParametricCurveRequest
    created: SketchExecReceipt | None = None
    inspected: SketchExecInspection | None = None

    def apply(self, doc: SketchDocument) -> None:
        self.created = apply_sketch_add_parametric_curve(doc, self.request, self.collaborators)

    def inspect(self, doc: SketchReadDocument) -> None:
        if self.created is None:
            raise SketchAddParametricCurveError(
                "INVALID_SKETCH_ADD_PARAMETRIC_CURVE_RESULT",
                "sketch_add_parametric_curve did not return an identity receipt",
            )
        self.inspected = read_sketch_add_parametric_curve_result(doc, self.created)

    def run(self) -> SketchAddParametricCurveResult:
        result = run_sketch_add_parametric_curve_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_add_parametric_curve_uncertain(
                "SKETCH_ADD_PARAMETRIC_CURVE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected sketch_add_parametric_curve result",
                committed=True,
            )
        return make_sketch_add_parametric_curve_success(SketchName(self.inspected.sketch_name), self.inspected.geometry_index, self.inspected.sample_count)


def run_sketch_add_parametric_curve(
    collaborators: SketchAddParametricCurveCollaborators,
    doc_name: object, sketch_name: object, x_expr: object, y_expr: object, t_start: object, t_end: object, samples: object, construction: object,
) -> SketchAddParametricCurveResult:
    request = build_sketch_add_parametric_curve_request(doc_name, sketch_name, x_expr, y_expr, t_start, t_end, samples, construction)
    if isinstance(request, dict):
        return request
    return _SketchAddParametricCurveExecution(collaborators, request).run()


class _SketchAddParametricCurveRpcFacade(Protocol):
    _cad_collaborators: SketchAddParametricCurveCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sketch_add_parametric_curve(
    self: _SketchAddParametricCurveRpcFacade, doc_name: str, sketch_name: str, x_expr: str, y_expr: str, t_start: float, t_end: float, samples: int = 100, construction: bool = False,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_add_parametric_curve(collaborators, doc_name, sketch_name, x_expr, y_expr, t_start, t_end, samples, construction)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_add_parametric_curve", rpc_sketch_add_parametric_curve)


__all__ = [
    "SketchAddParametricCurveCollaborators",
    "SketchAddParametricCurveError",
    "apply_sketch_add_parametric_curve",
    "build_sketch_add_parametric_curve_request",
    "read_sketch_add_parametric_curve_result",
    "rpc_sketch_add_parametric_curve",
    "run_sketch_add_parametric_curve",
    "TYPED_RPC_HANDLER",
]
