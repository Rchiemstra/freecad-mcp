"""Typed ``sketch_import_points`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

try:
    from ...._shared.protocol.sketch_import_points_contract import (
        SketchImportPointsCollaborators,
        SketchImportPointsFailure,
        SketchImportPointsRequest,
        SketchImportPointsResult,
        DocumentName,
        SketchDocument,
        SketchName,
        SketchObject,
        SketchReadDocument,
        make_sketch_import_points_failure,
        make_sketch_import_points_success,
        make_sketch_import_points_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.sketch_import_points_contract import (
        SketchImportPointsCollaborators,
        SketchImportPointsFailure,
        SketchImportPointsRequest,
        SketchImportPointsResult,
        DocumentName,
        SketchDocument,
        SketchName,
        SketchObject,
        SketchReadDocument,
        make_sketch_import_points_failure,
        make_sketch_import_points_success,
        make_sketch_import_points_uncertain,
    )
from .sketch_import_points_mutation import SketchImportPointsError, run_sketch_import_points_native_mutation


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


def _failure(error: SketchImportPointsError, *, retry_safe: bool = True) -> SketchImportPointsFailure:
    return make_sketch_import_points_failure(error.code, str(error), retry_safe=retry_safe)


def _require_name(value: object, field: str) -> str | SketchImportPointsFailure:
    if not isinstance(value, str) or not value.strip():
        return _failure(SketchImportPointsError("INVALID_ARGUMENT", f"{field} must be a nonempty string"))
    return value


def _require_float(value: object, field: str) -> float | SketchImportPointsFailure:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _failure(SketchImportPointsError("INVALID_ARGUMENT", f"{field} must be a number"))
    return float(value)


def _require_int(value: object, field: str) -> int | SketchImportPointsFailure:
    if type(value) is not int:
        return _failure(SketchImportPointsError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_bool(value: object, field: str, *, default: bool) -> bool | SketchImportPointsFailure:
    if value is None:
        return default
    if type(value) is not bool:
        return _failure(SketchImportPointsError("INVALID_ARGUMENT", f"{field} must be a boolean"))
    return value


def _require_optional_int(value: object, field: str) -> int | None | SketchImportPointsFailure:
    if value is None:
        return None
    if type(value) is not int:
        return _failure(SketchImportPointsError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_optional_str(value: object, field: str) -> str | None | SketchImportPointsFailure:
    if value is None:
        return None
    if not isinstance(value, str):
        return _failure(SketchImportPointsError("INVALID_ARGUMENT", f"{field} must be a string"))
    return value


def _require_points(
    value: object, field: str, *, min_count: int
) -> tuple[tuple[float, float], ...] | SketchImportPointsFailure:
    if not isinstance(value, list):
        return _failure(SketchImportPointsError("INVALID_ARGUMENT", f"{field} must be a list of points"))
    points: list[tuple[float, float]] = []
    for item in value:
        if not isinstance(item, dict):
            return _failure(SketchImportPointsError("INVALID_ARGUMENT", f"{field} entries must be objects"))
        x_value = _require_float(item.get("x"), f"{field}.x")
        y_value = _require_float(item.get("y"), f"{field}.y")
        if isinstance(x_value, dict):
            return x_value
        if isinstance(y_value, dict):
            return y_value
        points.append((x_value, y_value))
    if len(points) < min_count:
        return _failure(SketchImportPointsError("INVALID_ARGUMENT", f"{field} requires at least {min_count} points"))
    return tuple(points)


def _require_int_list(value: object, field: str) -> tuple[int, ...] | SketchImportPointsFailure:
    if not isinstance(value, list) or not value:
        return _failure(SketchImportPointsError("INVALID_ARGUMENT", f"{field} must be a nonempty list of integers"))
    indices: list[int] = []
    for item in value:
        parsed = _require_int(item, field)
        if isinstance(parsed, dict):
            return parsed
        indices.append(parsed)
    return tuple(indices)


def _require_optional_floats(value: object, field: str) -> tuple[float, ...] | None | SketchImportPointsFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchImportPointsError("INVALID_ARGUMENT", f"{field} must be a list of numbers"))
    numbers: list[float] = []
    for item in value:
        parsed = _require_float(item, field)
        if isinstance(parsed, dict):
            return parsed
        numbers.append(parsed)
    return tuple(numbers)


def _require_optional_ints(value: object, field: str) -> tuple[int, ...] | None | SketchImportPointsFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchImportPointsError("INVALID_ARGUMENT", f"{field} must be a list of integers"))
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
        raise SketchImportPointsError("SKETCH_NOT_FOUND", f"Sketch not found: {sketch_name!r}")
    if not _is_sketch(sketch):
        raise SketchImportPointsError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {sketch_name!r}")
    return sketch

def build_sketch_import_points_request(doc_name: object, sketch_name: object, points: object, construction: object) -> SketchImportPointsRequest | SketchImportPointsFailure:
    doc_name_value = _require_name(doc_name, 'doc_name')
    if isinstance(doc_name_value, dict):
        return doc_name_value
    sketch_name_value = _require_name(sketch_name, 'sketch_name')
    if isinstance(sketch_name_value, dict):
        return sketch_name_value
    points_value = _require_points(points, 'points', min_count=1)
    if isinstance(points_value, dict):
        return points_value
    construction_value = _require_bool(construction, 'construction', default=False)
    if isinstance(construction_value, dict):
        return construction_value
    return SketchImportPointsRequest(
        doc_name=DocumentName(doc_name_value),
        sketch_name=SketchName(sketch_name_value),
        points=points_value,
        construction=construction_value,
    )

def apply_sketch_import_points(
    doc: SketchDocument,
    request: SketchImportPointsRequest,
    collaborators: SketchImportPointsCollaborators,
) -> SketchExecReceipt:
    """Mutate the sketch without recomputing or managing a transaction."""

    sketch = _require_sketch(doc, request.sketch_name)
    before_geo = sketch.GeometryCount
    before_con = sketch.ConstraintCount
    last = -1
    for x, y in request.points:
        last = int(
            sketch.addGeometry(
                collaborators.part.Point(collaborators.freecad.Vector(x, y, 0.0)),
                request.construction,
            )
        )
    return SketchExecReceipt(
        name=sketch.Name,
        sketch=sketch,
        geometry_index=last,
        geometry_count_before=before_geo,
        constraint_count_before=before_con,
        sample_count=0,
    )

def read_sketch_import_points_result(doc: SketchReadDocument, receipt: SketchExecReceipt) -> SketchExecInspection:
    sketch = doc.getObject(receipt.name)
    if sketch is None:
        raise SketchImportPointsError("SKETCH_MISSING", f"Sketch is missing: {receipt.name!r}")
    if sketch is not receipt.sketch:
        raise SketchImportPointsError("SKETCH_REPLACED", f"Sketch was replaced before commit: {receipt.name!r}")
    if not _is_sketch(sketch):
        raise SketchImportPointsError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {receipt.name!r}")
    if sketch.GeometryCount <= receipt.geometry_count_before:
        raise SketchImportPointsError(
            "GEOMETRY_MISSING",
            f"Created sketch geometry is missing: {receipt.name!r}",
        )
    indices = list(range(receipt.geometry_count_before, sketch.GeometryCount))
    return SketchExecInspection(
        sketch_name=SketchName(receipt.name),
        geometry_index=receipt.geometry_index,
        geometry_indices=indices,
        constraint_index=receipt.geometry_index,
        sample_count=receipt.sample_count,
    )


@dataclass(slots=True)
class _SketchImportPointsExecution:
    collaborators: SketchImportPointsCollaborators
    request: SketchImportPointsRequest
    created: SketchExecReceipt | None = None
    inspected: SketchExecInspection | None = None

    def apply(self, doc: SketchDocument) -> None:
        self.created = apply_sketch_import_points(doc, self.request, self.collaborators)

    def inspect(self, doc: SketchReadDocument) -> None:
        if self.created is None:
            raise SketchImportPointsError(
                "INVALID_SKETCH_IMPORT_POINTS_RESULT",
                "sketch_import_points did not return an identity receipt",
            )
        self.inspected = read_sketch_import_points_result(doc, self.created)

    def run(self) -> SketchImportPointsResult:
        result = run_sketch_import_points_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_import_points_uncertain(
                "SKETCH_IMPORT_POINTS_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected sketch_import_points result",
                committed=True,
            )
        return make_sketch_import_points_success(SketchName(self.inspected.sketch_name), self.inspected.geometry_indices)


def run_sketch_import_points(
    collaborators: SketchImportPointsCollaborators,
    doc_name: object, sketch_name: object, points: object, construction: object,
) -> SketchImportPointsResult:
    request = build_sketch_import_points_request(doc_name, sketch_name, points, construction)
    if isinstance(request, dict):
        return request
    return _SketchImportPointsExecution(collaborators, request).run()


class _SketchImportPointsRpcFacade(Protocol):
    _cad_collaborators: SketchImportPointsCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sketch_import_points(
    self: _SketchImportPointsRpcFacade, doc_name: str, sketch_name: str, points: list[dict[str, float]], construction: bool = False,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_import_points(collaborators, doc_name, sketch_name, points, construction)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_import_points", rpc_sketch_import_points)


__all__ = [
    "SketchImportPointsCollaborators",
    "SketchImportPointsError",
    "apply_sketch_import_points",
    "build_sketch_import_points_request",
    "read_sketch_import_points_result",
    "rpc_sketch_import_points",
    "run_sketch_import_points",
    "TYPED_RPC_HANDLER",
]
