"""Typed ``sketch_constrain_parallel`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

try:
    from ...._shared.protocol.sketch_constrain_parallel_contract import (
        SketchConstrainParallelCollaborators,
        SketchConstrainParallelFailure,
        SketchConstrainParallelRequest,
        SketchConstrainParallelResult,
        DocumentName,
        SketchDocument,
        SketchName,
        SketchObject,
        SketchReadDocument,
        make_sketch_constrain_parallel_failure,
        make_sketch_constrain_parallel_success,
        make_sketch_constrain_parallel_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.sketch_constrain_parallel_contract import (
        SketchConstrainParallelCollaborators,
        SketchConstrainParallelFailure,
        SketchConstrainParallelRequest,
        SketchConstrainParallelResult,
        DocumentName,
        SketchDocument,
        SketchName,
        SketchObject,
        SketchReadDocument,
        make_sketch_constrain_parallel_failure,
        make_sketch_constrain_parallel_success,
        make_sketch_constrain_parallel_uncertain,
    )
from .sketch_constrain_parallel_mutation import SketchConstrainParallelError, run_sketch_constrain_parallel_native_mutation


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


def _failure(error: SketchConstrainParallelError, *, retry_safe: bool = True) -> SketchConstrainParallelFailure:
    return make_sketch_constrain_parallel_failure(error.code, str(error), retry_safe=retry_safe)


def _require_name(value: object, field: str) -> str | SketchConstrainParallelFailure:
    if not isinstance(value, str) or not value.strip():
        return _failure(SketchConstrainParallelError("INVALID_ARGUMENT", f"{field} must be a nonempty string"))
    return value


def _require_float(value: object, field: str) -> float | SketchConstrainParallelFailure:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _failure(SketchConstrainParallelError("INVALID_ARGUMENT", f"{field} must be a number"))
    return float(value)


def _require_int(value: object, field: str) -> int | SketchConstrainParallelFailure:
    if type(value) is not int:
        return _failure(SketchConstrainParallelError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_bool(value: object, field: str, *, default: bool) -> bool | SketchConstrainParallelFailure:
    if value is None:
        return default
    if type(value) is not bool:
        return _failure(SketchConstrainParallelError("INVALID_ARGUMENT", f"{field} must be a boolean"))
    return value


def _require_optional_int(value: object, field: str) -> int | None | SketchConstrainParallelFailure:
    if value is None:
        return None
    if type(value) is not int:
        return _failure(SketchConstrainParallelError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_optional_str(value: object, field: str) -> str | None | SketchConstrainParallelFailure:
    if value is None:
        return None
    if not isinstance(value, str):
        return _failure(SketchConstrainParallelError("INVALID_ARGUMENT", f"{field} must be a string"))
    return value


def _require_points(
    value: object, field: str, *, min_count: int
) -> tuple[tuple[float, float], ...] | SketchConstrainParallelFailure:
    if not isinstance(value, list):
        return _failure(SketchConstrainParallelError("INVALID_ARGUMENT", f"{field} must be a list of points"))
    points: list[tuple[float, float]] = []
    for item in value:
        if not isinstance(item, dict):
            return _failure(SketchConstrainParallelError("INVALID_ARGUMENT", f"{field} entries must be objects"))
        x_value = _require_float(item.get("x"), f"{field}.x")
        y_value = _require_float(item.get("y"), f"{field}.y")
        if isinstance(x_value, dict):
            return x_value
        if isinstance(y_value, dict):
            return y_value
        points.append((x_value, y_value))
    if len(points) < min_count:
        return _failure(SketchConstrainParallelError("INVALID_ARGUMENT", f"{field} requires at least {min_count} points"))
    return tuple(points)


def _require_int_list(value: object, field: str) -> tuple[int, ...] | SketchConstrainParallelFailure:
    if not isinstance(value, list) or not value:
        return _failure(SketchConstrainParallelError("INVALID_ARGUMENT", f"{field} must be a nonempty list of integers"))
    indices: list[int] = []
    for item in value:
        parsed = _require_int(item, field)
        if isinstance(parsed, dict):
            return parsed
        indices.append(parsed)
    return tuple(indices)


def _require_optional_floats(value: object, field: str) -> tuple[float, ...] | None | SketchConstrainParallelFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchConstrainParallelError("INVALID_ARGUMENT", f"{field} must be a list of numbers"))
    numbers: list[float] = []
    for item in value:
        parsed = _require_float(item, field)
        if isinstance(parsed, dict):
            return parsed
        numbers.append(parsed)
    return tuple(numbers)


def _require_optional_ints(value: object, field: str) -> tuple[int, ...] | None | SketchConstrainParallelFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchConstrainParallelError("INVALID_ARGUMENT", f"{field} must be a list of integers"))
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
        raise SketchConstrainParallelError("SKETCH_NOT_FOUND", f"Sketch not found: {sketch_name!r}")
    if not _is_sketch(sketch):
        raise SketchConstrainParallelError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {sketch_name!r}")
    return sketch

def build_sketch_constrain_parallel_request(doc_name: object, sketch_name: object, geo1: object, geo2: object) -> SketchConstrainParallelRequest | SketchConstrainParallelFailure:
    doc_name_value = _require_name(doc_name, 'doc_name')
    if isinstance(doc_name_value, dict):
        return doc_name_value
    sketch_name_value = _require_name(sketch_name, 'sketch_name')
    if isinstance(sketch_name_value, dict):
        return sketch_name_value
    geo1_value = _require_int(geo1, 'geo1')
    if isinstance(geo1_value, dict):
        return geo1_value
    geo2_value = _require_int(geo2, 'geo2')
    if isinstance(geo2_value, dict):
        return geo2_value
    return SketchConstrainParallelRequest(
        doc_name=DocumentName(doc_name_value),
        sketch_name=SketchName(sketch_name_value),
        geo1=geo1_value,
        geo2=geo2_value,
    )

def apply_sketch_constrain_parallel(
    doc: SketchDocument,
    request: SketchConstrainParallelRequest,
    collaborators: SketchConstrainParallelCollaborators,
) -> SketchExecReceipt:
    """Mutate the sketch without recomputing or managing a transaction."""

    sketch = _require_sketch(doc, request.sketch_name)
    before_geo = sketch.GeometryCount
    before_con = sketch.ConstraintCount
    idx = sketch.addConstraint(
        collaborators.sketcher.Constraint("Parallel", request.geo1, request.geo2)
    )
    return SketchExecReceipt(
        name=sketch.Name,
        sketch=sketch,
        geometry_index=int(idx),
        geometry_count_before=before_geo,
        constraint_count_before=before_con,
        sample_count=0,
    )

def read_sketch_constrain_parallel_result(doc: SketchReadDocument, receipt: SketchExecReceipt) -> SketchExecInspection:
    sketch = doc.getObject(receipt.name)
    if sketch is None:
        raise SketchConstrainParallelError("SKETCH_MISSING", f"Sketch is missing: {receipt.name!r}")
    if sketch is not receipt.sketch:
        raise SketchConstrainParallelError("SKETCH_REPLACED", f"Sketch was replaced before commit: {receipt.name!r}")
    if not _is_sketch(sketch):
        raise SketchConstrainParallelError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {receipt.name!r}")
    if sketch.ConstraintCount <= receipt.constraint_count_before:
        raise SketchConstrainParallelError(
            "CONSTRAINT_MISSING",
            f"Created sketch constraint is missing: {receipt.name!r}",
        )
    return SketchExecInspection(
        sketch_name=SketchName(receipt.name),
        geometry_index=receipt.geometry_index,
        geometry_indices=[receipt.geometry_index] if receipt.geometry_index >= 0 else [],
        constraint_index=receipt.geometry_index,
        sample_count=receipt.sample_count,
    )


@dataclass(slots=True)
class _SketchConstrainParallelExecution:
    collaborators: SketchConstrainParallelCollaborators
    request: SketchConstrainParallelRequest
    created: SketchExecReceipt | None = None
    inspected: SketchExecInspection | None = None

    def apply(self, doc: SketchDocument) -> None:
        self.created = apply_sketch_constrain_parallel(doc, self.request, self.collaborators)

    def inspect(self, doc: SketchReadDocument) -> None:
        if self.created is None:
            raise SketchConstrainParallelError(
                "INVALID_SKETCH_CONSTRAIN_PARALLEL_RESULT",
                "sketch_constrain_parallel did not return an identity receipt",
            )
        self.inspected = read_sketch_constrain_parallel_result(doc, self.created)

    def run(self) -> SketchConstrainParallelResult:
        result = run_sketch_constrain_parallel_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_constrain_parallel_uncertain(
                "SKETCH_CONSTRAIN_PARALLEL_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected sketch_constrain_parallel result",
                committed=True,
            )
        return make_sketch_constrain_parallel_success(SketchName(self.inspected.sketch_name), self.inspected.constraint_index)


def run_sketch_constrain_parallel(
    collaborators: SketchConstrainParallelCollaborators,
    doc_name: object, sketch_name: object, geo1: object, geo2: object,
) -> SketchConstrainParallelResult:
    request = build_sketch_constrain_parallel_request(doc_name, sketch_name, geo1, geo2)
    if isinstance(request, dict):
        return request
    return _SketchConstrainParallelExecution(collaborators, request).run()


class _SketchConstrainParallelRpcFacade(Protocol):
    _cad_collaborators: SketchConstrainParallelCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sketch_constrain_parallel(
    self: _SketchConstrainParallelRpcFacade, doc_name: str, sketch_name: str, geo1: int, geo2: int,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_constrain_parallel(collaborators, doc_name, sketch_name, geo1, geo2)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_constrain_parallel", rpc_sketch_constrain_parallel)


__all__ = [
    "SketchConstrainParallelCollaborators",
    "SketchConstrainParallelError",
    "apply_sketch_constrain_parallel",
    "build_sketch_constrain_parallel_request",
    "read_sketch_constrain_parallel_result",
    "rpc_sketch_constrain_parallel",
    "run_sketch_constrain_parallel",
    "TYPED_RPC_HANDLER",
]
