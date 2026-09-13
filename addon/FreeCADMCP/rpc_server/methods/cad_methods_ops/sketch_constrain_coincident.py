"""Typed ``sketch_constrain_coincident`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.sketch_constrain_coincident_contract import (
    SketchConstrainCoincidentCollaborators,
    SketchConstrainCoincidentFailure,
    SketchConstrainCoincidentRequest,
    SketchConstrainCoincidentResult,
    DocumentName,
    SketchDocument,
    SketchName,
    SketchObject,
    SketchReadDocument,
    make_sketch_constrain_coincident_failure,
    make_sketch_constrain_coincident_success,
    make_sketch_constrain_coincident_uncertain,
)
from .sketch_constrain_coincident_mutation import SketchConstrainCoincidentError, run_sketch_constrain_coincident_native_mutation


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


def _failure(error: SketchConstrainCoincidentError, *, retry_safe: bool = True) -> SketchConstrainCoincidentFailure:
    return make_sketch_constrain_coincident_failure(error.code, str(error), retry_safe=retry_safe)


def _require_name(value: object, field: str) -> str | SketchConstrainCoincidentFailure:
    if not isinstance(value, str) or not value.strip():
        return _failure(SketchConstrainCoincidentError("INVALID_ARGUMENT", f"{field} must be a nonempty string"))
    return value


def _require_float(value: object, field: str) -> float | SketchConstrainCoincidentFailure:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _failure(SketchConstrainCoincidentError("INVALID_ARGUMENT", f"{field} must be a number"))
    return float(value)


def _require_int(value: object, field: str) -> int | SketchConstrainCoincidentFailure:
    if type(value) is not int:
        return _failure(SketchConstrainCoincidentError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_bool(value: object, field: str, *, default: bool) -> bool | SketchConstrainCoincidentFailure:
    if value is None:
        return default
    if type(value) is not bool:
        return _failure(SketchConstrainCoincidentError("INVALID_ARGUMENT", f"{field} must be a boolean"))
    return value


def _require_optional_int(value: object, field: str) -> int | None | SketchConstrainCoincidentFailure:
    if value is None:
        return None
    if type(value) is not int:
        return _failure(SketchConstrainCoincidentError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_optional_str(value: object, field: str) -> str | None | SketchConstrainCoincidentFailure:
    if value is None:
        return None
    if not isinstance(value, str):
        return _failure(SketchConstrainCoincidentError("INVALID_ARGUMENT", f"{field} must be a string"))
    return value


def _require_points(
    value: object, field: str, *, min_count: int
) -> tuple[tuple[float, float], ...] | SketchConstrainCoincidentFailure:
    if not isinstance(value, list):
        return _failure(SketchConstrainCoincidentError("INVALID_ARGUMENT", f"{field} must be a list of points"))
    points: list[tuple[float, float]] = []
    for item in value:
        if not isinstance(item, dict):
            return _failure(SketchConstrainCoincidentError("INVALID_ARGUMENT", f"{field} entries must be objects"))
        x_value = _require_float(item.get("x"), f"{field}.x")
        y_value = _require_float(item.get("y"), f"{field}.y")
        if isinstance(x_value, dict):
            return x_value
        if isinstance(y_value, dict):
            return y_value
        points.append((x_value, y_value))
    if len(points) < min_count:
        return _failure(SketchConstrainCoincidentError("INVALID_ARGUMENT", f"{field} requires at least {min_count} points"))
    return tuple(points)


def _require_int_list(value: object, field: str) -> tuple[int, ...] | SketchConstrainCoincidentFailure:
    if not isinstance(value, list) or not value:
        return _failure(SketchConstrainCoincidentError("INVALID_ARGUMENT", f"{field} must be a nonempty list of integers"))
    indices: list[int] = []
    for item in value:
        parsed = _require_int(item, field)
        if isinstance(parsed, dict):
            return parsed
        indices.append(parsed)
    return tuple(indices)


def _require_optional_floats(value: object, field: str) -> tuple[float, ...] | None | SketchConstrainCoincidentFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchConstrainCoincidentError("INVALID_ARGUMENT", f"{field} must be a list of numbers"))
    numbers: list[float] = []
    for item in value:
        parsed = _require_float(item, field)
        if isinstance(parsed, dict):
            return parsed
        numbers.append(parsed)
    return tuple(numbers)


def _require_optional_ints(value: object, field: str) -> tuple[int, ...] | None | SketchConstrainCoincidentFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchConstrainCoincidentError("INVALID_ARGUMENT", f"{field} must be a list of integers"))
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
        raise SketchConstrainCoincidentError("SKETCH_NOT_FOUND", f"Sketch not found: {sketch_name!r}")
    if not _is_sketch(sketch):
        raise SketchConstrainCoincidentError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {sketch_name!r}")
    return sketch

def build_sketch_constrain_coincident_request(doc_name: object, sketch_name: object, geo1: object, pos1: object, geo2: object, pos2: object) -> SketchConstrainCoincidentRequest | SketchConstrainCoincidentFailure:
    doc_name_value = _require_name(doc_name, 'doc_name')
    if isinstance(doc_name_value, dict):
        return doc_name_value
    sketch_name_value = _require_name(sketch_name, 'sketch_name')
    if isinstance(sketch_name_value, dict):
        return sketch_name_value
    geo1_value = _require_int(geo1, 'geo1')
    if isinstance(geo1_value, dict):
        return geo1_value
    pos1_value = _require_int(pos1, 'pos1')
    if isinstance(pos1_value, dict):
        return pos1_value
    geo2_value = _require_int(geo2, 'geo2')
    if isinstance(geo2_value, dict):
        return geo2_value
    pos2_value = _require_int(pos2, 'pos2')
    if isinstance(pos2_value, dict):
        return pos2_value
    return SketchConstrainCoincidentRequest(
        doc_name=DocumentName(doc_name_value),
        sketch_name=SketchName(sketch_name_value),
        geo1=geo1_value,
        pos1=pos1_value,
        geo2=geo2_value,
        pos2=pos2_value,
    )

def apply_sketch_constrain_coincident(
    doc: SketchDocument,
    request: SketchConstrainCoincidentRequest,
    collaborators: SketchConstrainCoincidentCollaborators,
) -> SketchExecReceipt:
    """Mutate the sketch without recomputing or managing a transaction."""

    sketch = _require_sketch(doc, request.sketch_name)
    before_geo = sketch.GeometryCount
    before_con = sketch.ConstraintCount
    idx = sketch.addConstraint(
        collaborators.sketcher.Constraint(
            "Coincident", request.geo1, request.pos1, request.geo2, request.pos2
        )
    )
    return SketchExecReceipt(
        name=sketch.Name,
        sketch=sketch,
        geometry_index=int(idx),
        geometry_count_before=before_geo,
        constraint_count_before=before_con,
        sample_count=0,
    )

def read_sketch_constrain_coincident_result(doc: SketchReadDocument, receipt: SketchExecReceipt) -> SketchExecInspection:
    sketch = doc.getObject(receipt.name)
    if sketch is None:
        raise SketchConstrainCoincidentError("SKETCH_MISSING", f"Sketch is missing: {receipt.name!r}")
    if sketch is not receipt.sketch:
        raise SketchConstrainCoincidentError("SKETCH_REPLACED", f"Sketch was replaced before commit: {receipt.name!r}")
    if not _is_sketch(sketch):
        raise SketchConstrainCoincidentError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {receipt.name!r}")
    if sketch.ConstraintCount <= receipt.constraint_count_before:
        raise SketchConstrainCoincidentError(
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
class _SketchConstrainCoincidentExecution:
    collaborators: SketchConstrainCoincidentCollaborators
    request: SketchConstrainCoincidentRequest
    created: SketchExecReceipt | None = None
    inspected: SketchExecInspection | None = None

    def apply(self, doc: SketchDocument) -> None:
        self.created = apply_sketch_constrain_coincident(doc, self.request, self.collaborators)

    def inspect(self, doc: SketchReadDocument) -> None:
        if self.created is None:
            raise SketchConstrainCoincidentError(
                "INVALID_SKETCH_CONSTRAIN_COINCIDENT_RESULT",
                "sketch_constrain_coincident did not return an identity receipt",
            )
        self.inspected = read_sketch_constrain_coincident_result(doc, self.created)

    def run(self) -> SketchConstrainCoincidentResult:
        result = run_sketch_constrain_coincident_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_constrain_coincident_uncertain(
                "SKETCH_CONSTRAIN_COINCIDENT_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected sketch_constrain_coincident result",
                committed=True,
            )
        return make_sketch_constrain_coincident_success(SketchName(self.inspected.sketch_name), self.inspected.constraint_index)


def run_sketch_constrain_coincident(
    collaborators: SketchConstrainCoincidentCollaborators,
    doc_name: object, sketch_name: object, geo1: object, pos1: object, geo2: object, pos2: object,
) -> SketchConstrainCoincidentResult:
    request = build_sketch_constrain_coincident_request(doc_name, sketch_name, geo1, pos1, geo2, pos2)
    if isinstance(request, dict):
        return request
    return _SketchConstrainCoincidentExecution(collaborators, request).run()


class _SketchConstrainCoincidentRpcFacade(Protocol):
    _cad_collaborators: SketchConstrainCoincidentCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sketch_constrain_coincident(
    self: _SketchConstrainCoincidentRpcFacade, doc_name: str, sketch_name: str, geo1: int, pos1: int, geo2: int, pos2: int,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_constrain_coincident(collaborators, doc_name, sketch_name, geo1, pos1, geo2, pos2)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_constrain_coincident", rpc_sketch_constrain_coincident)


__all__ = [
    "SketchConstrainCoincidentCollaborators",
    "SketchConstrainCoincidentError",
    "apply_sketch_constrain_coincident",
    "build_sketch_constrain_coincident_request",
    "read_sketch_constrain_coincident_result",
    "rpc_sketch_constrain_coincident",
    "run_sketch_constrain_coincident",
    "TYPED_RPC_HANDLER",
]
