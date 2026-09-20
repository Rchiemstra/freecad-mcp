"""Typed ``sketch_trim`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

try:
    from ...._shared.protocol.sketch_trim_contract import (
        SketchTrimCollaborators,
        SketchTrimFailure,
        SketchTrimRequest,
        SketchTrimResult,
        DocumentName,
        SketchDocument,
        SketchName,
        SketchObject,
        SketchReadDocument,
        make_sketch_trim_failure,
        make_sketch_trim_success,
        make_sketch_trim_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.sketch_trim_contract import (
        SketchTrimCollaborators,
        SketchTrimFailure,
        SketchTrimRequest,
        SketchTrimResult,
        DocumentName,
        SketchDocument,
        SketchName,
        SketchObject,
        SketchReadDocument,
        make_sketch_trim_failure,
        make_sketch_trim_success,
        make_sketch_trim_uncertain,
    )
from .sketch_trim_mutation import SketchTrimError, run_sketch_trim_native_mutation


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


def _failure(error: SketchTrimError, *, retry_safe: bool = True) -> SketchTrimFailure:
    return make_sketch_trim_failure(error.code, str(error), retry_safe=retry_safe)


def _require_name(value: object, field: str) -> str | SketchTrimFailure:
    if not isinstance(value, str) or not value.strip():
        return _failure(SketchTrimError("INVALID_ARGUMENT", f"{field} must be a nonempty string"))
    return value


def _require_float(value: object, field: str) -> float | SketchTrimFailure:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _failure(SketchTrimError("INVALID_ARGUMENT", f"{field} must be a number"))
    return float(value)


def _require_int(value: object, field: str) -> int | SketchTrimFailure:
    if type(value) is not int:
        return _failure(SketchTrimError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_bool(value: object, field: str, *, default: bool) -> bool | SketchTrimFailure:
    if value is None:
        return default
    if type(value) is not bool:
        return _failure(SketchTrimError("INVALID_ARGUMENT", f"{field} must be a boolean"))
    return value


def _require_optional_int(value: object, field: str) -> int | None | SketchTrimFailure:
    if value is None:
        return None
    if type(value) is not int:
        return _failure(SketchTrimError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_optional_str(value: object, field: str) -> str | None | SketchTrimFailure:
    if value is None:
        return None
    if not isinstance(value, str):
        return _failure(SketchTrimError("INVALID_ARGUMENT", f"{field} must be a string"))
    return value


def _require_points(
    value: object, field: str, *, min_count: int
) -> tuple[tuple[float, float], ...] | SketchTrimFailure:
    if not isinstance(value, list):
        return _failure(SketchTrimError("INVALID_ARGUMENT", f"{field} must be a list of points"))
    points: list[tuple[float, float]] = []
    for item in value:
        if not isinstance(item, dict):
            return _failure(SketchTrimError("INVALID_ARGUMENT", f"{field} entries must be objects"))
        x_value = _require_float(item.get("x"), f"{field}.x")
        y_value = _require_float(item.get("y"), f"{field}.y")
        if isinstance(x_value, dict):
            return x_value
        if isinstance(y_value, dict):
            return y_value
        points.append((x_value, y_value))
    if len(points) < min_count:
        return _failure(SketchTrimError("INVALID_ARGUMENT", f"{field} requires at least {min_count} points"))
    return tuple(points)


def _require_int_list(value: object, field: str) -> tuple[int, ...] | SketchTrimFailure:
    if not isinstance(value, list) or not value:
        return _failure(SketchTrimError("INVALID_ARGUMENT", f"{field} must be a nonempty list of integers"))
    indices: list[int] = []
    for item in value:
        parsed = _require_int(item, field)
        if isinstance(parsed, dict):
            return parsed
        indices.append(parsed)
    return tuple(indices)


def _require_optional_floats(value: object, field: str) -> tuple[float, ...] | None | SketchTrimFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchTrimError("INVALID_ARGUMENT", f"{field} must be a list of numbers"))
    numbers: list[float] = []
    for item in value:
        parsed = _require_float(item, field)
        if isinstance(parsed, dict):
            return parsed
        numbers.append(parsed)
    return tuple(numbers)


def _require_optional_ints(value: object, field: str) -> tuple[int, ...] | None | SketchTrimFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchTrimError("INVALID_ARGUMENT", f"{field} must be a list of integers"))
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
        raise SketchTrimError("SKETCH_NOT_FOUND", f"Sketch not found: {sketch_name!r}")
    if not _is_sketch(sketch):
        raise SketchTrimError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {sketch_name!r}")
    return sketch

def build_sketch_trim_request(doc_name: object, sketch_name: object, geo_index: object, point_x: object, point_y: object) -> SketchTrimRequest | SketchTrimFailure:
    doc_name_value = _require_name(doc_name, 'doc_name')
    if isinstance(doc_name_value, dict):
        return doc_name_value
    sketch_name_value = _require_name(sketch_name, 'sketch_name')
    if isinstance(sketch_name_value, dict):
        return sketch_name_value
    geo_index_value = _require_int(geo_index, 'geo_index')
    if isinstance(geo_index_value, dict):
        return geo_index_value
    point_x_value = _require_float(point_x, 'point_x')
    if isinstance(point_x_value, dict):
        return point_x_value
    point_y_value = _require_float(point_y, 'point_y')
    if isinstance(point_y_value, dict):
        return point_y_value
    return SketchTrimRequest(
        doc_name=DocumentName(doc_name_value),
        sketch_name=SketchName(sketch_name_value),
        geo_index=geo_index_value,
        point_x=point_x_value,
        point_y=point_y_value,
    )

def apply_sketch_trim(
    doc: SketchDocument,
    request: SketchTrimRequest,
    collaborators: SketchTrimCollaborators,
) -> SketchExecReceipt:
    """Mutate the sketch without recomputing or managing a transaction."""

    sketch = _require_sketch(doc, request.sketch_name)
    before_geo = sketch.GeometryCount
    before_con = sketch.ConstraintCount
    sketch.trim(
        request.geo_index,
        collaborators.freecad.Vector(request.point_x, request.point_y, 0.0),
    )
    return SketchExecReceipt(
        name=sketch.Name,
        sketch=sketch,
        geometry_index=request.geo_index,
        geometry_count_before=before_geo,
        constraint_count_before=before_con,
        sample_count=0,
    )

def read_sketch_trim_result(doc: SketchReadDocument, receipt: SketchExecReceipt) -> SketchExecInspection:
    sketch = doc.getObject(receipt.name)
    if sketch is None:
        raise SketchTrimError("SKETCH_MISSING", f"Sketch is missing: {receipt.name!r}")
    if sketch is not receipt.sketch:
        raise SketchTrimError("SKETCH_REPLACED", f"Sketch was replaced before commit: {receipt.name!r}")
    if not _is_sketch(sketch):
        raise SketchTrimError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {receipt.name!r}")
    return SketchExecInspection(
        sketch_name=SketchName(receipt.name),
        geometry_index=receipt.geometry_index,
        geometry_indices=[receipt.geometry_index] if receipt.geometry_index >= 0 else [],
        constraint_index=receipt.geometry_index,
        sample_count=receipt.sample_count,
    )


@dataclass(slots=True)
class _SketchTrimExecution:
    collaborators: SketchTrimCollaborators
    request: SketchTrimRequest
    created: SketchExecReceipt | None = None
    inspected: SketchExecInspection | None = None

    def apply(self, doc: SketchDocument) -> None:
        self.created = apply_sketch_trim(doc, self.request, self.collaborators)

    def inspect(self, doc: SketchReadDocument) -> None:
        if self.created is None:
            raise SketchTrimError(
                "INVALID_SKETCH_TRIM_RESULT",
                "sketch_trim did not return an identity receipt",
            )
        self.inspected = read_sketch_trim_result(doc, self.created)

    def run(self) -> SketchTrimResult:
        result = run_sketch_trim_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_trim_uncertain(
                "SKETCH_TRIM_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected sketch_trim result",
                committed=True,
            )
        return make_sketch_trim_success(SketchName(self.inspected.sketch_name))


def run_sketch_trim(
    collaborators: SketchTrimCollaborators,
    doc_name: object, sketch_name: object, geo_index: object, point_x: object, point_y: object,
) -> SketchTrimResult:
    request = build_sketch_trim_request(doc_name, sketch_name, geo_index, point_x, point_y)
    if isinstance(request, dict):
        return request
    return _SketchTrimExecution(collaborators, request).run()


class _SketchTrimRpcFacade(Protocol):
    _cad_collaborators: SketchTrimCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sketch_trim(
    self: _SketchTrimRpcFacade, doc_name: str, sketch_name: str, geo_index: int, point_x: float, point_y: float,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_trim(collaborators, doc_name, sketch_name, geo_index, point_x, point_y)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_trim", rpc_sketch_trim)


__all__ = [
    "SketchTrimCollaborators",
    "SketchTrimError",
    "apply_sketch_trim",
    "build_sketch_trim_request",
    "read_sketch_trim_result",
    "rpc_sketch_trim",
    "run_sketch_trim",
    "TYPED_RPC_HANDLER",
]
