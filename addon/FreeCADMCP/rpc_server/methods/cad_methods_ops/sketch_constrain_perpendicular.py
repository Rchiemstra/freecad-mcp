"""Typed ``sketch_constrain_perpendicular`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.sketch_constrain_perpendicular_contract import (
    SketchConstrainPerpendicularCollaborators,
    SketchConstrainPerpendicularFailure,
    SketchConstrainPerpendicularRequest,
    SketchConstrainPerpendicularResult,
    DocumentName,
    SketchDocument,
    SketchName,
    SketchObject,
    SketchReadDocument,
    make_sketch_constrain_perpendicular_failure,
    make_sketch_constrain_perpendicular_success,
    make_sketch_constrain_perpendicular_uncertain,
)
from .sketch_constrain_perpendicular_mutation import SketchConstrainPerpendicularError, run_sketch_constrain_perpendicular_native_mutation


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


def _failure(error: SketchConstrainPerpendicularError, *, retry_safe: bool = True) -> SketchConstrainPerpendicularFailure:
    return make_sketch_constrain_perpendicular_failure(error.code, str(error), retry_safe=retry_safe)


def _require_name(value: object, field: str) -> str | SketchConstrainPerpendicularFailure:
    if not isinstance(value, str) or not value.strip():
        return _failure(SketchConstrainPerpendicularError("INVALID_ARGUMENT", f"{field} must be a nonempty string"))
    return value


def _require_float(value: object, field: str) -> float | SketchConstrainPerpendicularFailure:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _failure(SketchConstrainPerpendicularError("INVALID_ARGUMENT", f"{field} must be a number"))
    return float(value)


def _require_int(value: object, field: str) -> int | SketchConstrainPerpendicularFailure:
    if type(value) is not int:
        return _failure(SketchConstrainPerpendicularError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_bool(value: object, field: str, *, default: bool) -> bool | SketchConstrainPerpendicularFailure:
    if value is None:
        return default
    if type(value) is not bool:
        return _failure(SketchConstrainPerpendicularError("INVALID_ARGUMENT", f"{field} must be a boolean"))
    return value


def _require_optional_int(value: object, field: str) -> int | None | SketchConstrainPerpendicularFailure:
    if value is None:
        return None
    if type(value) is not int:
        return _failure(SketchConstrainPerpendicularError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_optional_str(value: object, field: str) -> str | None | SketchConstrainPerpendicularFailure:
    if value is None:
        return None
    if not isinstance(value, str):
        return _failure(SketchConstrainPerpendicularError("INVALID_ARGUMENT", f"{field} must be a string"))
    return value


def _require_points(
    value: object, field: str, *, min_count: int
) -> tuple[tuple[float, float], ...] | SketchConstrainPerpendicularFailure:
    if not isinstance(value, list):
        return _failure(SketchConstrainPerpendicularError("INVALID_ARGUMENT", f"{field} must be a list of points"))
    points: list[tuple[float, float]] = []
    for item in value:
        if not isinstance(item, dict):
            return _failure(SketchConstrainPerpendicularError("INVALID_ARGUMENT", f"{field} entries must be objects"))
        x_value = _require_float(item.get("x"), f"{field}.x")
        y_value = _require_float(item.get("y"), f"{field}.y")
        if isinstance(x_value, dict):
            return x_value
        if isinstance(y_value, dict):
            return y_value
        points.append((x_value, y_value))
    if len(points) < min_count:
        return _failure(SketchConstrainPerpendicularError("INVALID_ARGUMENT", f"{field} requires at least {min_count} points"))
    return tuple(points)


def _require_int_list(value: object, field: str) -> tuple[int, ...] | SketchConstrainPerpendicularFailure:
    if not isinstance(value, list) or not value:
        return _failure(SketchConstrainPerpendicularError("INVALID_ARGUMENT", f"{field} must be a nonempty list of integers"))
    indices: list[int] = []
    for item in value:
        parsed = _require_int(item, field)
        if isinstance(parsed, dict):
            return parsed
        indices.append(parsed)
    return tuple(indices)


def _require_optional_floats(value: object, field: str) -> tuple[float, ...] | None | SketchConstrainPerpendicularFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchConstrainPerpendicularError("INVALID_ARGUMENT", f"{field} must be a list of numbers"))
    numbers: list[float] = []
    for item in value:
        parsed = _require_float(item, field)
        if isinstance(parsed, dict):
            return parsed
        numbers.append(parsed)
    return tuple(numbers)


def _require_optional_ints(value: object, field: str) -> tuple[int, ...] | None | SketchConstrainPerpendicularFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchConstrainPerpendicularError("INVALID_ARGUMENT", f"{field} must be a list of integers"))
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
        raise SketchConstrainPerpendicularError("SKETCH_NOT_FOUND", f"Sketch not found: {sketch_name!r}")
    if not _is_sketch(sketch):
        raise SketchConstrainPerpendicularError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {sketch_name!r}")
    return sketch

def build_sketch_constrain_perpendicular_request(doc_name: object, sketch_name: object, geo1: object, geo2: object) -> SketchConstrainPerpendicularRequest | SketchConstrainPerpendicularFailure:
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
    return SketchConstrainPerpendicularRequest(
        doc_name=DocumentName(doc_name_value),
        sketch_name=SketchName(sketch_name_value),
        geo1=geo1_value,
        geo2=geo2_value,
    )

def apply_sketch_constrain_perpendicular(
    doc: SketchDocument,
    request: SketchConstrainPerpendicularRequest,
    collaborators: SketchConstrainPerpendicularCollaborators,
) -> SketchExecReceipt:
    """Mutate the sketch without recomputing or managing a transaction."""

    sketch = _require_sketch(doc, request.sketch_name)
    before_geo = sketch.GeometryCount
    before_con = sketch.ConstraintCount
    idx = sketch.addConstraint(
        collaborators.sketcher.Constraint("Perpendicular", request.geo1, request.geo2)
    )
    return SketchExecReceipt(
        name=sketch.Name,
        sketch=sketch,
        geometry_index=int(idx),
        geometry_count_before=before_geo,
        constraint_count_before=before_con,
        sample_count=0,
    )

def read_sketch_constrain_perpendicular_result(doc: SketchReadDocument, receipt: SketchExecReceipt) -> SketchExecInspection:
    sketch = doc.getObject(receipt.name)
    if sketch is None:
        raise SketchConstrainPerpendicularError("SKETCH_MISSING", f"Sketch is missing: {receipt.name!r}")
    if sketch is not receipt.sketch:
        raise SketchConstrainPerpendicularError("SKETCH_REPLACED", f"Sketch was replaced before commit: {receipt.name!r}")
    if not _is_sketch(sketch):
        raise SketchConstrainPerpendicularError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {receipt.name!r}")
    if sketch.ConstraintCount <= receipt.constraint_count_before:
        raise SketchConstrainPerpendicularError(
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
class _SketchConstrainPerpendicularExecution:
    collaborators: SketchConstrainPerpendicularCollaborators
    request: SketchConstrainPerpendicularRequest
    created: SketchExecReceipt | None = None
    inspected: SketchExecInspection | None = None

    def apply(self, doc: SketchDocument) -> None:
        self.created = apply_sketch_constrain_perpendicular(doc, self.request, self.collaborators)

    def inspect(self, doc: SketchReadDocument) -> None:
        if self.created is None:
            raise SketchConstrainPerpendicularError(
                "INVALID_SKETCH_CONSTRAIN_PERPENDICULAR_RESULT",
                "sketch_constrain_perpendicular did not return an identity receipt",
            )
        self.inspected = read_sketch_constrain_perpendicular_result(doc, self.created)

    def run(self) -> SketchConstrainPerpendicularResult:
        result = run_sketch_constrain_perpendicular_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_constrain_perpendicular_uncertain(
                "SKETCH_CONSTRAIN_PERPENDICULAR_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected sketch_constrain_perpendicular result",
                committed=True,
            )
        return make_sketch_constrain_perpendicular_success(SketchName(self.inspected.sketch_name), self.inspected.constraint_index)


def run_sketch_constrain_perpendicular(
    collaborators: SketchConstrainPerpendicularCollaborators,
    doc_name: object, sketch_name: object, geo1: object, geo2: object,
) -> SketchConstrainPerpendicularResult:
    request = build_sketch_constrain_perpendicular_request(doc_name, sketch_name, geo1, geo2)
    if isinstance(request, dict):
        return request
    return _SketchConstrainPerpendicularExecution(collaborators, request).run()


class _SketchConstrainPerpendicularRpcFacade(Protocol):
    _cad_collaborators: SketchConstrainPerpendicularCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sketch_constrain_perpendicular(
    self: _SketchConstrainPerpendicularRpcFacade, doc_name: str, sketch_name: str, geo1: int, geo2: int,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_constrain_perpendicular(collaborators, doc_name, sketch_name, geo1, geo2)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_constrain_perpendicular", rpc_sketch_constrain_perpendicular)


__all__ = [
    "SketchConstrainPerpendicularCollaborators",
    "SketchConstrainPerpendicularError",
    "apply_sketch_constrain_perpendicular",
    "build_sketch_constrain_perpendicular_request",
    "read_sketch_constrain_perpendicular_result",
    "rpc_sketch_constrain_perpendicular",
    "run_sketch_constrain_perpendicular",
    "TYPED_RPC_HANDLER",
]
