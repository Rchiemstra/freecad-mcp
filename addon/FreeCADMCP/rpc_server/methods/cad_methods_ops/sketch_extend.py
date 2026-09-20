"""Typed ``sketch_extend`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

try:
    from ...._shared.protocol.sketch_extend_contract import (
        SketchExtendCollaborators,
        SketchExtendFailure,
        SketchExtendRequest,
        SketchExtendResult,
        DocumentName,
        SketchDocument,
        SketchName,
        SketchObject,
        SketchReadDocument,
        make_sketch_extend_failure,
        make_sketch_extend_success,
        make_sketch_extend_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.sketch_extend_contract import (
        SketchExtendCollaborators,
        SketchExtendFailure,
        SketchExtendRequest,
        SketchExtendResult,
        DocumentName,
        SketchDocument,
        SketchName,
        SketchObject,
        SketchReadDocument,
        make_sketch_extend_failure,
        make_sketch_extend_success,
        make_sketch_extend_uncertain,
    )
from .sketch_extend_mutation import SketchExtendError, run_sketch_extend_native_mutation


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


def _failure(error: SketchExtendError, *, retry_safe: bool = True) -> SketchExtendFailure:
    return make_sketch_extend_failure(error.code, str(error), retry_safe=retry_safe)


def _require_name(value: object, field: str) -> str | SketchExtendFailure:
    if not isinstance(value, str) or not value.strip():
        return _failure(SketchExtendError("INVALID_ARGUMENT", f"{field} must be a nonempty string"))
    return value


def _require_float(value: object, field: str) -> float | SketchExtendFailure:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _failure(SketchExtendError("INVALID_ARGUMENT", f"{field} must be a number"))
    return float(value)


def _require_int(value: object, field: str) -> int | SketchExtendFailure:
    if type(value) is not int:
        return _failure(SketchExtendError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_bool(value: object, field: str, *, default: bool) -> bool | SketchExtendFailure:
    if value is None:
        return default
    if type(value) is not bool:
        return _failure(SketchExtendError("INVALID_ARGUMENT", f"{field} must be a boolean"))
    return value


def _require_optional_int(value: object, field: str) -> int | None | SketchExtendFailure:
    if value is None:
        return None
    if type(value) is not int:
        return _failure(SketchExtendError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_optional_str(value: object, field: str) -> str | None | SketchExtendFailure:
    if value is None:
        return None
    if not isinstance(value, str):
        return _failure(SketchExtendError("INVALID_ARGUMENT", f"{field} must be a string"))
    return value


def _require_points(
    value: object, field: str, *, min_count: int
) -> tuple[tuple[float, float], ...] | SketchExtendFailure:
    if not isinstance(value, list):
        return _failure(SketchExtendError("INVALID_ARGUMENT", f"{field} must be a list of points"))
    points: list[tuple[float, float]] = []
    for item in value:
        if not isinstance(item, dict):
            return _failure(SketchExtendError("INVALID_ARGUMENT", f"{field} entries must be objects"))
        x_value = _require_float(item.get("x"), f"{field}.x")
        y_value = _require_float(item.get("y"), f"{field}.y")
        if isinstance(x_value, dict):
            return x_value
        if isinstance(y_value, dict):
            return y_value
        points.append((x_value, y_value))
    if len(points) < min_count:
        return _failure(SketchExtendError("INVALID_ARGUMENT", f"{field} requires at least {min_count} points"))
    return tuple(points)


def _require_int_list(value: object, field: str) -> tuple[int, ...] | SketchExtendFailure:
    if not isinstance(value, list) or not value:
        return _failure(SketchExtendError("INVALID_ARGUMENT", f"{field} must be a nonempty list of integers"))
    indices: list[int] = []
    for item in value:
        parsed = _require_int(item, field)
        if isinstance(parsed, dict):
            return parsed
        indices.append(parsed)
    return tuple(indices)


def _require_optional_floats(value: object, field: str) -> tuple[float, ...] | None | SketchExtendFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchExtendError("INVALID_ARGUMENT", f"{field} must be a list of numbers"))
    numbers: list[float] = []
    for item in value:
        parsed = _require_float(item, field)
        if isinstance(parsed, dict):
            return parsed
        numbers.append(parsed)
    return tuple(numbers)


def _require_optional_ints(value: object, field: str) -> tuple[int, ...] | None | SketchExtendFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchExtendError("INVALID_ARGUMENT", f"{field} must be a list of integers"))
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
        raise SketchExtendError("SKETCH_NOT_FOUND", f"Sketch not found: {sketch_name!r}")
    if not _is_sketch(sketch):
        raise SketchExtendError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {sketch_name!r}")
    return sketch

def build_sketch_extend_request(doc_name: object, sketch_name: object, geo_index: object, increment: object, end_point: object) -> SketchExtendRequest | SketchExtendFailure:
    doc_name_value = _require_name(doc_name, 'doc_name')
    if isinstance(doc_name_value, dict):
        return doc_name_value
    sketch_name_value = _require_name(sketch_name, 'sketch_name')
    if isinstance(sketch_name_value, dict):
        return sketch_name_value
    geo_index_value = _require_int(geo_index, 'geo_index')
    if isinstance(geo_index_value, dict):
        return geo_index_value
    increment_value = _require_float(increment, 'increment')
    if isinstance(increment_value, dict):
        return increment_value
    end_point_value = _require_int(end_point, 'end_point')
    if isinstance(end_point_value, dict):
        return end_point_value
    return SketchExtendRequest(
        doc_name=DocumentName(doc_name_value),
        sketch_name=SketchName(sketch_name_value),
        geo_index=geo_index_value,
        increment=increment_value,
        end_point=end_point_value,
    )

def apply_sketch_extend(
    doc: SketchDocument,
    request: SketchExtendRequest,
    collaborators: SketchExtendCollaborators,
) -> SketchExecReceipt:
    """Mutate the sketch without recomputing or managing a transaction."""

    sketch = _require_sketch(doc, request.sketch_name)
    before_geo = sketch.GeometryCount
    before_con = sketch.ConstraintCount
    sketch.extend(request.geo_index, request.increment, request.end_point)
    return SketchExecReceipt(
        name=sketch.Name,
        sketch=sketch,
        geometry_index=request.geo_index,
        geometry_count_before=before_geo,
        constraint_count_before=before_con,
        sample_count=0,
    )

def read_sketch_extend_result(doc: SketchReadDocument, receipt: SketchExecReceipt) -> SketchExecInspection:
    sketch = doc.getObject(receipt.name)
    if sketch is None:
        raise SketchExtendError("SKETCH_MISSING", f"Sketch is missing: {receipt.name!r}")
    if sketch is not receipt.sketch:
        raise SketchExtendError("SKETCH_REPLACED", f"Sketch was replaced before commit: {receipt.name!r}")
    if not _is_sketch(sketch):
        raise SketchExtendError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {receipt.name!r}")
    return SketchExecInspection(
        sketch_name=SketchName(receipt.name),
        geometry_index=receipt.geometry_index,
        geometry_indices=[receipt.geometry_index] if receipt.geometry_index >= 0 else [],
        constraint_index=receipt.geometry_index,
        sample_count=receipt.sample_count,
    )


@dataclass(slots=True)
class _SketchExtendExecution:
    collaborators: SketchExtendCollaborators
    request: SketchExtendRequest
    created: SketchExecReceipt | None = None
    inspected: SketchExecInspection | None = None

    def apply(self, doc: SketchDocument) -> None:
        self.created = apply_sketch_extend(doc, self.request, self.collaborators)

    def inspect(self, doc: SketchReadDocument) -> None:
        if self.created is None:
            raise SketchExtendError(
                "INVALID_SKETCH_EXTEND_RESULT",
                "sketch_extend did not return an identity receipt",
            )
        self.inspected = read_sketch_extend_result(doc, self.created)

    def run(self) -> SketchExtendResult:
        result = run_sketch_extend_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_extend_uncertain(
                "SKETCH_EXTEND_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected sketch_extend result",
                committed=True,
            )
        return make_sketch_extend_success(SketchName(self.inspected.sketch_name))


def run_sketch_extend(
    collaborators: SketchExtendCollaborators,
    doc_name: object, sketch_name: object, geo_index: object, increment: object, end_point: object,
) -> SketchExtendResult:
    request = build_sketch_extend_request(doc_name, sketch_name, geo_index, increment, end_point)
    if isinstance(request, dict):
        return request
    return _SketchExtendExecution(collaborators, request).run()


class _SketchExtendRpcFacade(Protocol):
    _cad_collaborators: SketchExtendCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sketch_extend(
    self: _SketchExtendRpcFacade, doc_name: str, sketch_name: str, geo_index: int, increment: float, end_point: int = 2,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_extend(collaborators, doc_name, sketch_name, geo_index, increment, end_point)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_extend", rpc_sketch_extend)


__all__ = [
    "SketchExtendCollaborators",
    "SketchExtendError",
    "apply_sketch_extend",
    "build_sketch_extend_request",
    "read_sketch_extend_result",
    "rpc_sketch_extend",
    "run_sketch_extend",
    "TYPED_RPC_HANDLER",
]
