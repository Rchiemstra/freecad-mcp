"""Typed ``sketch_symmetry`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.sketch_symmetry_contract import (
    SketchSymmetryCollaborators,
    SketchSymmetryFailure,
    SketchSymmetryRequest,
    SketchSymmetryResult,
    DocumentName,
    SketchDocument,
    SketchName,
    SketchObject,
    SketchReadDocument,
    make_sketch_symmetry_failure,
    make_sketch_symmetry_success,
    make_sketch_symmetry_uncertain,
)
from .sketch_symmetry_mutation import SketchSymmetryError, run_sketch_symmetry_native_mutation


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


def _failure(error: SketchSymmetryError, *, retry_safe: bool = True) -> SketchSymmetryFailure:
    return make_sketch_symmetry_failure(error.code, str(error), retry_safe=retry_safe)


def _require_name(value: object, field: str) -> str | SketchSymmetryFailure:
    if not isinstance(value, str) or not value.strip():
        return _failure(SketchSymmetryError("INVALID_ARGUMENT", f"{field} must be a nonempty string"))
    return value


def _require_float(value: object, field: str) -> float | SketchSymmetryFailure:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _failure(SketchSymmetryError("INVALID_ARGUMENT", f"{field} must be a number"))
    return float(value)


def _require_int(value: object, field: str) -> int | SketchSymmetryFailure:
    if type(value) is not int:
        return _failure(SketchSymmetryError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_bool(value: object, field: str, *, default: bool) -> bool | SketchSymmetryFailure:
    if value is None:
        return default
    if type(value) is not bool:
        return _failure(SketchSymmetryError("INVALID_ARGUMENT", f"{field} must be a boolean"))
    return value


def _require_optional_int(value: object, field: str) -> int | None | SketchSymmetryFailure:
    if value is None:
        return None
    if type(value) is not int:
        return _failure(SketchSymmetryError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_optional_str(value: object, field: str) -> str | None | SketchSymmetryFailure:
    if value is None:
        return None
    if not isinstance(value, str):
        return _failure(SketchSymmetryError("INVALID_ARGUMENT", f"{field} must be a string"))
    return value


def _require_points(
    value: object, field: str, *, min_count: int
) -> tuple[tuple[float, float], ...] | SketchSymmetryFailure:
    if not isinstance(value, list):
        return _failure(SketchSymmetryError("INVALID_ARGUMENT", f"{field} must be a list of points"))
    points: list[tuple[float, float]] = []
    for item in value:
        if not isinstance(item, dict):
            return _failure(SketchSymmetryError("INVALID_ARGUMENT", f"{field} entries must be objects"))
        x_value = _require_float(item.get("x"), f"{field}.x")
        y_value = _require_float(item.get("y"), f"{field}.y")
        if isinstance(x_value, dict):
            return x_value
        if isinstance(y_value, dict):
            return y_value
        points.append((x_value, y_value))
    if len(points) < min_count:
        return _failure(SketchSymmetryError("INVALID_ARGUMENT", f"{field} requires at least {min_count} points"))
    return tuple(points)


def _require_int_list(value: object, field: str) -> tuple[int, ...] | SketchSymmetryFailure:
    if not isinstance(value, list) or not value:
        return _failure(SketchSymmetryError("INVALID_ARGUMENT", f"{field} must be a nonempty list of integers"))
    indices: list[int] = []
    for item in value:
        parsed = _require_int(item, field)
        if isinstance(parsed, dict):
            return parsed
        indices.append(parsed)
    return tuple(indices)


def _require_optional_floats(value: object, field: str) -> tuple[float, ...] | None | SketchSymmetryFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchSymmetryError("INVALID_ARGUMENT", f"{field} must be a list of numbers"))
    numbers: list[float] = []
    for item in value:
        parsed = _require_float(item, field)
        if isinstance(parsed, dict):
            return parsed
        numbers.append(parsed)
    return tuple(numbers)


def _require_optional_ints(value: object, field: str) -> tuple[int, ...] | None | SketchSymmetryFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchSymmetryError("INVALID_ARGUMENT", f"{field} must be a list of integers"))
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
        raise SketchSymmetryError("SKETCH_NOT_FOUND", f"Sketch not found: {sketch_name!r}")
    if not _is_sketch(sketch):
        raise SketchSymmetryError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {sketch_name!r}")
    return sketch

def build_sketch_symmetry_request(doc_name: object, sketch_name: object, geo_indices: object, symmetry_geo: object, copy: object) -> SketchSymmetryRequest | SketchSymmetryFailure:
    doc_name_value = _require_name(doc_name, 'doc_name')
    if isinstance(doc_name_value, dict):
        return doc_name_value
    sketch_name_value = _require_name(sketch_name, 'sketch_name')
    if isinstance(sketch_name_value, dict):
        return sketch_name_value
    geo_indices_value = _require_int_list(geo_indices, 'geo_indices')
    if isinstance(geo_indices_value, dict):
        return geo_indices_value
    symmetry_geo_value = _require_int(symmetry_geo, 'symmetry_geo')
    if isinstance(symmetry_geo_value, dict):
        return symmetry_geo_value
    copy_value = _require_bool(copy, 'copy', default=True)
    if isinstance(copy_value, dict):
        return copy_value
    return SketchSymmetryRequest(
        doc_name=DocumentName(doc_name_value),
        sketch_name=SketchName(sketch_name_value),
        geo_indices=geo_indices_value,
        symmetry_geo=symmetry_geo_value,
        copy=copy_value,
    )

def apply_sketch_symmetry(
    doc: SketchDocument,
    request: SketchSymmetryRequest,
    collaborators: SketchSymmetryCollaborators,
) -> SketchExecReceipt:
    """Mutate the sketch without recomputing or managing a transaction."""

    sketch = _require_sketch(doc, request.sketch_name)
    before_geo = sketch.GeometryCount
    before_con = sketch.ConstraintCount
    try:
        sketch.addSymmetric(list(request.geo_indices), request.symmetry_geo)
    except AttributeError:
        for geo_index in request.geo_indices:
            sketch.addConstraint(
                collaborators.sketcher.Constraint(
                    "Symmetric", geo_index, 1, geo_index, 2, request.symmetry_geo
                )
            )
    return SketchExecReceipt(
        name=sketch.Name,
        sketch=sketch,
        geometry_index=-1,
        geometry_count_before=before_geo,
        constraint_count_before=before_con,
        sample_count=0,
    )

def read_sketch_symmetry_result(doc: SketchReadDocument, receipt: SketchExecReceipt) -> SketchExecInspection:
    sketch = doc.getObject(receipt.name)
    if sketch is None:
        raise SketchSymmetryError("SKETCH_MISSING", f"Sketch is missing: {receipt.name!r}")
    if sketch is not receipt.sketch:
        raise SketchSymmetryError("SKETCH_REPLACED", f"Sketch was replaced before commit: {receipt.name!r}")
    if not _is_sketch(sketch):
        raise SketchSymmetryError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {receipt.name!r}")
    return SketchExecInspection(
        sketch_name=SketchName(receipt.name),
        geometry_index=receipt.geometry_index,
        geometry_indices=[receipt.geometry_index] if receipt.geometry_index >= 0 else [],
        constraint_index=receipt.geometry_index,
        sample_count=receipt.sample_count,
    )


@dataclass(slots=True)
class _SketchSymmetryExecution:
    collaborators: SketchSymmetryCollaborators
    request: SketchSymmetryRequest
    created: SketchExecReceipt | None = None
    inspected: SketchExecInspection | None = None

    def apply(self, doc: SketchDocument) -> None:
        self.created = apply_sketch_symmetry(doc, self.request, self.collaborators)

    def inspect(self, doc: SketchReadDocument) -> None:
        if self.created is None:
            raise SketchSymmetryError(
                "INVALID_SKETCH_SYMMETRY_RESULT",
                "sketch_symmetry did not return an identity receipt",
            )
        self.inspected = read_sketch_symmetry_result(doc, self.created)

    def run(self) -> SketchSymmetryResult:
        result = run_sketch_symmetry_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_symmetry_uncertain(
                "SKETCH_SYMMETRY_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected sketch_symmetry result",
                committed=True,
            )
        return make_sketch_symmetry_success(SketchName(self.inspected.sketch_name))


def run_sketch_symmetry(
    collaborators: SketchSymmetryCollaborators,
    doc_name: object, sketch_name: object, geo_indices: object, symmetry_geo: object, copy: object,
) -> SketchSymmetryResult:
    request = build_sketch_symmetry_request(doc_name, sketch_name, geo_indices, symmetry_geo, copy)
    if isinstance(request, dict):
        return request
    return _SketchSymmetryExecution(collaborators, request).run()


class _SketchSymmetryRpcFacade(Protocol):
    _cad_collaborators: SketchSymmetryCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sketch_symmetry(
    self: _SketchSymmetryRpcFacade, doc_name: str, sketch_name: str, geo_indices: list[int], symmetry_geo: int, copy: bool = True,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_symmetry(collaborators, doc_name, sketch_name, geo_indices, symmetry_geo, copy)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_symmetry", rpc_sketch_symmetry)


__all__ = [
    "SketchSymmetryCollaborators",
    "SketchSymmetryError",
    "apply_sketch_symmetry",
    "build_sketch_symmetry_request",
    "read_sketch_symmetry_result",
    "rpc_sketch_symmetry",
    "run_sketch_symmetry",
    "TYPED_RPC_HANDLER",
]
