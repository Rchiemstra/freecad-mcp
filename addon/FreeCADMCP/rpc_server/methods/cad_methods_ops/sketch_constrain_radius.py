"""Typed ``sketch_constrain_radius`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

try:
    from ...._shared.protocol.sketch_constrain_radius_contract import (
        SketchConstrainRadiusCollaborators,
        SketchConstrainRadiusFailure,
        SketchConstrainRadiusRequest,
        SketchConstrainRadiusResult,
        DocumentName,
        SketchDocument,
        SketchName,
        SketchObject,
        SketchReadDocument,
        make_sketch_constrain_radius_failure,
        make_sketch_constrain_radius_success,
        make_sketch_constrain_radius_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.sketch_constrain_radius_contract import (
        SketchConstrainRadiusCollaborators,
        SketchConstrainRadiusFailure,
        SketchConstrainRadiusRequest,
        SketchConstrainRadiusResult,
        DocumentName,
        SketchDocument,
        SketchName,
        SketchObject,
        SketchReadDocument,
        make_sketch_constrain_radius_failure,
        make_sketch_constrain_radius_success,
        make_sketch_constrain_radius_uncertain,
    )
from .sketch_constrain_radius_mutation import SketchConstrainRadiusError, run_sketch_constrain_radius_native_mutation


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


def _failure(error: SketchConstrainRadiusError, *, retry_safe: bool = True) -> SketchConstrainRadiusFailure:
    return make_sketch_constrain_radius_failure(error.code, str(error), retry_safe=retry_safe)


def _require_name(value: object, field: str) -> str | SketchConstrainRadiusFailure:
    if not isinstance(value, str) or not value.strip():
        return _failure(SketchConstrainRadiusError("INVALID_ARGUMENT", f"{field} must be a nonempty string"))
    return value


def _require_float(value: object, field: str) -> float | SketchConstrainRadiusFailure:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _failure(SketchConstrainRadiusError("INVALID_ARGUMENT", f"{field} must be a number"))
    return float(value)


def _require_int(value: object, field: str) -> int | SketchConstrainRadiusFailure:
    if type(value) is not int:
        return _failure(SketchConstrainRadiusError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_bool(value: object, field: str, *, default: bool) -> bool | SketchConstrainRadiusFailure:
    if value is None:
        return default
    if type(value) is not bool:
        return _failure(SketchConstrainRadiusError("INVALID_ARGUMENT", f"{field} must be a boolean"))
    return value


def _require_optional_int(value: object, field: str) -> int | None | SketchConstrainRadiusFailure:
    if value is None:
        return None
    if type(value) is not int:
        return _failure(SketchConstrainRadiusError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_optional_str(value: object, field: str) -> str | None | SketchConstrainRadiusFailure:
    if value is None:
        return None
    if not isinstance(value, str):
        return _failure(SketchConstrainRadiusError("INVALID_ARGUMENT", f"{field} must be a string"))
    return value


def _require_points(
    value: object, field: str, *, min_count: int
) -> tuple[tuple[float, float], ...] | SketchConstrainRadiusFailure:
    if not isinstance(value, list):
        return _failure(SketchConstrainRadiusError("INVALID_ARGUMENT", f"{field} must be a list of points"))
    points: list[tuple[float, float]] = []
    for item in value:
        if not isinstance(item, dict):
            return _failure(SketchConstrainRadiusError("INVALID_ARGUMENT", f"{field} entries must be objects"))
        x_value = _require_float(item.get("x"), f"{field}.x")
        y_value = _require_float(item.get("y"), f"{field}.y")
        if isinstance(x_value, dict):
            return x_value
        if isinstance(y_value, dict):
            return y_value
        points.append((x_value, y_value))
    if len(points) < min_count:
        return _failure(SketchConstrainRadiusError("INVALID_ARGUMENT", f"{field} requires at least {min_count} points"))
    return tuple(points)


def _require_int_list(value: object, field: str) -> tuple[int, ...] | SketchConstrainRadiusFailure:
    if not isinstance(value, list) or not value:
        return _failure(SketchConstrainRadiusError("INVALID_ARGUMENT", f"{field} must be a nonempty list of integers"))
    indices: list[int] = []
    for item in value:
        parsed = _require_int(item, field)
        if isinstance(parsed, dict):
            return parsed
        indices.append(parsed)
    return tuple(indices)


def _require_optional_floats(value: object, field: str) -> tuple[float, ...] | None | SketchConstrainRadiusFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchConstrainRadiusError("INVALID_ARGUMENT", f"{field} must be a list of numbers"))
    numbers: list[float] = []
    for item in value:
        parsed = _require_float(item, field)
        if isinstance(parsed, dict):
            return parsed
        numbers.append(parsed)
    return tuple(numbers)


def _require_optional_ints(value: object, field: str) -> tuple[int, ...] | None | SketchConstrainRadiusFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchConstrainRadiusError("INVALID_ARGUMENT", f"{field} must be a list of integers"))
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
        raise SketchConstrainRadiusError("SKETCH_NOT_FOUND", f"Sketch not found: {sketch_name!r}")
    if not _is_sketch(sketch):
        raise SketchConstrainRadiusError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {sketch_name!r}")
    return sketch

def build_sketch_constrain_radius_request(doc_name: object, sketch_name: object, geo: object, value: object, name: object) -> SketchConstrainRadiusRequest | SketchConstrainRadiusFailure:
    doc_name_value = _require_name(doc_name, 'doc_name')
    if isinstance(doc_name_value, dict):
        return doc_name_value
    sketch_name_value = _require_name(sketch_name, 'sketch_name')
    if isinstance(sketch_name_value, dict):
        return sketch_name_value
    geo_value = _require_int(geo, 'geo')
    if isinstance(geo_value, dict):
        return geo_value
    value_value = _require_float(value, 'value')
    if isinstance(value_value, dict):
        return value_value
    name_value = _require_optional_str(name, 'name')
    if isinstance(name_value, dict):
        return name_value
    return SketchConstrainRadiusRequest(
        doc_name=DocumentName(doc_name_value),
        sketch_name=SketchName(sketch_name_value),
        geo=geo_value,
        value=value_value,
        name=name_value,
    )

def apply_sketch_constrain_radius(
    doc: SketchDocument,
    request: SketchConstrainRadiusRequest,
    collaborators: SketchConstrainRadiusCollaborators,
) -> SketchExecReceipt:
    """Mutate the sketch without recomputing or managing a transaction."""

    sketch = _require_sketch(doc, request.sketch_name)
    before_geo = sketch.GeometryCount
    before_con = sketch.ConstraintCount
    idx = sketch.addConstraint(
        collaborators.sketcher.Constraint("Radius", request.geo, request.value)
    )
    if request.name:
        sketch.renameConstraint(int(idx), request.name)
    return SketchExecReceipt(
        name=sketch.Name,
        sketch=sketch,
        geometry_index=int(idx),
        geometry_count_before=before_geo,
        constraint_count_before=before_con,
        sample_count=0,
    )

def read_sketch_constrain_radius_result(doc: SketchReadDocument, receipt: SketchExecReceipt) -> SketchExecInspection:
    sketch = doc.getObject(receipt.name)
    if sketch is None:
        raise SketchConstrainRadiusError("SKETCH_MISSING", f"Sketch is missing: {receipt.name!r}")
    if sketch is not receipt.sketch:
        raise SketchConstrainRadiusError("SKETCH_REPLACED", f"Sketch was replaced before commit: {receipt.name!r}")
    if not _is_sketch(sketch):
        raise SketchConstrainRadiusError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {receipt.name!r}")
    if sketch.ConstraintCount <= receipt.constraint_count_before:
        raise SketchConstrainRadiusError(
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
class _SketchConstrainRadiusExecution:
    collaborators: SketchConstrainRadiusCollaborators
    request: SketchConstrainRadiusRequest
    created: SketchExecReceipt | None = None
    inspected: SketchExecInspection | None = None

    def apply(self, doc: SketchDocument) -> None:
        self.created = apply_sketch_constrain_radius(doc, self.request, self.collaborators)

    def inspect(self, doc: SketchReadDocument) -> None:
        if self.created is None:
            raise SketchConstrainRadiusError(
                "INVALID_SKETCH_CONSTRAIN_RADIUS_RESULT",
                "sketch_constrain_radius did not return an identity receipt",
            )
        self.inspected = read_sketch_constrain_radius_result(doc, self.created)

    def run(self) -> SketchConstrainRadiusResult:
        result = run_sketch_constrain_radius_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_constrain_radius_uncertain(
                "SKETCH_CONSTRAIN_RADIUS_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected sketch_constrain_radius result",
                committed=True,
            )
        return make_sketch_constrain_radius_success(SketchName(self.inspected.sketch_name), self.inspected.constraint_index)


def run_sketch_constrain_radius(
    collaborators: SketchConstrainRadiusCollaborators,
    doc_name: object, sketch_name: object, geo: object, value: object, name: object,
) -> SketchConstrainRadiusResult:
    request = build_sketch_constrain_radius_request(doc_name, sketch_name, geo, value, name)
    if isinstance(request, dict):
        return request
    return _SketchConstrainRadiusExecution(collaborators, request).run()


class _SketchConstrainRadiusRpcFacade(Protocol):
    _cad_collaborators: SketchConstrainRadiusCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sketch_constrain_radius(
    self: _SketchConstrainRadiusRpcFacade, doc_name: str, sketch_name: str, geo: int, value: float, name: str | None = None,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_constrain_radius(collaborators, doc_name, sketch_name, geo, value, name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_constrain_radius", rpc_sketch_constrain_radius)


__all__ = [
    "SketchConstrainRadiusCollaborators",
    "SketchConstrainRadiusError",
    "apply_sketch_constrain_radius",
    "build_sketch_constrain_radius_request",
    "read_sketch_constrain_radius_result",
    "rpc_sketch_constrain_radius",
    "run_sketch_constrain_radius",
    "TYPED_RPC_HANDLER",
]
