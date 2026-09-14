"""Typed ``sketch_add_line`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.sketch_add_line_contract import (
    SketchAddLineCollaborators,
    SketchAddLineFailure,
    SketchAddLineRequest,
    SketchAddLineResult,
    DocumentName,
    SketchDocument,
    SketchName,
    SketchObject,
    SketchReadDocument,
    make_sketch_add_line_failure,
    make_sketch_add_line_success,
    make_sketch_add_line_uncertain,
)
from .sketch_add_line_mutation import SketchAddLineError, run_sketch_add_line_native_mutation


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


def _failure(error: SketchAddLineError, *, retry_safe: bool = True) -> SketchAddLineFailure:
    return make_sketch_add_line_failure(error.code, str(error), retry_safe=retry_safe)


def _require_name(value: object, field: str) -> str | SketchAddLineFailure:
    if not isinstance(value, str) or not value.strip():
        return _failure(SketchAddLineError("INVALID_ARGUMENT", f"{field} must be a nonempty string"))
    return value


def _require_float(value: object, field: str) -> float | SketchAddLineFailure:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _failure(SketchAddLineError("INVALID_ARGUMENT", f"{field} must be a number"))
    return float(value)


def _require_int(value: object, field: str) -> int | SketchAddLineFailure:
    if type(value) is not int:
        return _failure(SketchAddLineError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_bool(value: object, field: str, *, default: bool) -> bool | SketchAddLineFailure:
    if value is None:
        return default
    if type(value) is not bool:
        return _failure(SketchAddLineError("INVALID_ARGUMENT", f"{field} must be a boolean"))
    return value


def _require_optional_int(value: object, field: str) -> int | None | SketchAddLineFailure:
    if value is None:
        return None
    if type(value) is not int:
        return _failure(SketchAddLineError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_optional_str(value: object, field: str) -> str | None | SketchAddLineFailure:
    if value is None:
        return None
    if not isinstance(value, str):
        return _failure(SketchAddLineError("INVALID_ARGUMENT", f"{field} must be a string"))
    return value


def _require_points(
    value: object, field: str, *, min_count: int
) -> tuple[tuple[float, float], ...] | SketchAddLineFailure:
    if not isinstance(value, list):
        return _failure(SketchAddLineError("INVALID_ARGUMENT", f"{field} must be a list of points"))
    points: list[tuple[float, float]] = []
    for item in value:
        if not isinstance(item, dict):
            return _failure(SketchAddLineError("INVALID_ARGUMENT", f"{field} entries must be objects"))
        x_value = _require_float(item.get("x"), f"{field}.x")
        y_value = _require_float(item.get("y"), f"{field}.y")
        if isinstance(x_value, dict):
            return x_value
        if isinstance(y_value, dict):
            return y_value
        points.append((x_value, y_value))
    if len(points) < min_count:
        return _failure(SketchAddLineError("INVALID_ARGUMENT", f"{field} requires at least {min_count} points"))
    return tuple(points)


def _require_int_list(value: object, field: str) -> tuple[int, ...] | SketchAddLineFailure:
    if not isinstance(value, list) or not value:
        return _failure(SketchAddLineError("INVALID_ARGUMENT", f"{field} must be a nonempty list of integers"))
    indices: list[int] = []
    for item in value:
        parsed = _require_int(item, field)
        if isinstance(parsed, dict):
            return parsed
        indices.append(parsed)
    return tuple(indices)


def _require_optional_floats(value: object, field: str) -> tuple[float, ...] | None | SketchAddLineFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchAddLineError("INVALID_ARGUMENT", f"{field} must be a list of numbers"))
    numbers: list[float] = []
    for item in value:
        parsed = _require_float(item, field)
        if isinstance(parsed, dict):
            return parsed
        numbers.append(parsed)
    return tuple(numbers)


def _require_optional_ints(value: object, field: str) -> tuple[int, ...] | None | SketchAddLineFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchAddLineError("INVALID_ARGUMENT", f"{field} must be a list of integers"))
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
        raise SketchAddLineError("SKETCH_NOT_FOUND", f"Sketch not found: {sketch_name!r}")
    if not _is_sketch(sketch):
        raise SketchAddLineError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {sketch_name!r}")
    return sketch

def build_sketch_add_line_request(doc_name: object, sketch_name: object, x1: object, y1: object, x2: object, y2: object, construction: object) -> SketchAddLineRequest | SketchAddLineFailure:
    doc_name_value = _require_name(doc_name, 'doc_name')
    if isinstance(doc_name_value, dict):
        return doc_name_value
    sketch_name_value = _require_name(sketch_name, 'sketch_name')
    if isinstance(sketch_name_value, dict):
        return sketch_name_value
    x1_value = _require_float(x1, 'x1')
    if isinstance(x1_value, dict):
        return x1_value
    y1_value = _require_float(y1, 'y1')
    if isinstance(y1_value, dict):
        return y1_value
    x2_value = _require_float(x2, 'x2')
    if isinstance(x2_value, dict):
        return x2_value
    y2_value = _require_float(y2, 'y2')
    if isinstance(y2_value, dict):
        return y2_value
    construction_value = _require_bool(construction, 'construction', default=False)
    if isinstance(construction_value, dict):
        return construction_value
    return SketchAddLineRequest(
        doc_name=DocumentName(doc_name_value),
        sketch_name=SketchName(sketch_name_value),
        x1=x1_value,
        y1=y1_value,
        x2=x2_value,
        y2=y2_value,
        construction=construction_value,
    )

def apply_sketch_add_line(
    doc: SketchDocument,
    request: SketchAddLineRequest,
    collaborators: SketchAddLineCollaborators,
) -> SketchExecReceipt:
    """Mutate the sketch without recomputing or managing a transaction."""

    sketch = _require_sketch(doc, request.sketch_name)
    before_geo = sketch.GeometryCount
    before_con = sketch.ConstraintCount
    start = collaborators.freecad.Vector(request.x1, request.y1, 0.0)
    end = collaborators.freecad.Vector(request.x2, request.y2, 0.0)
    idx = sketch.addGeometry(
        collaborators.part.LineSegment(start, end), request.construction
    )
    return SketchExecReceipt(
        name=sketch.Name,
        sketch=sketch,
        geometry_index=int(idx),
        geometry_count_before=before_geo,
        constraint_count_before=before_con,
        sample_count=0,
    )

def read_sketch_add_line_result(doc: SketchReadDocument, receipt: SketchExecReceipt) -> SketchExecInspection:
    sketch = doc.getObject(receipt.name)
    if sketch is None:
        raise SketchAddLineError("SKETCH_MISSING", f"Sketch is missing: {receipt.name!r}")
    if sketch is not receipt.sketch:
        raise SketchAddLineError("SKETCH_REPLACED", f"Sketch was replaced before commit: {receipt.name!r}")
    if not _is_sketch(sketch):
        raise SketchAddLineError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {receipt.name!r}")
    if sketch.GeometryCount <= receipt.geometry_count_before:
        raise SketchAddLineError(
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
class _SketchAddLineExecution:
    collaborators: SketchAddLineCollaborators
    request: SketchAddLineRequest
    created: SketchExecReceipt | None = None
    inspected: SketchExecInspection | None = None

    def apply(self, doc: SketchDocument) -> None:
        self.created = apply_sketch_add_line(doc, self.request, self.collaborators)

    def inspect(self, doc: SketchReadDocument) -> None:
        if self.created is None:
            raise SketchAddLineError(
                "INVALID_SKETCH_ADD_LINE_RESULT",
                "sketch_add_line did not return an identity receipt",
            )
        self.inspected = read_sketch_add_line_result(doc, self.created)

    def run(self) -> SketchAddLineResult:
        result = run_sketch_add_line_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_add_line_uncertain(
                "SKETCH_ADD_LINE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected sketch_add_line result",
                committed=True,
            )
        return make_sketch_add_line_success(SketchName(self.inspected.sketch_name), self.inspected.geometry_index)


def run_sketch_add_line(
    collaborators: SketchAddLineCollaborators,
    doc_name: object, sketch_name: object, x1: object, y1: object, x2: object, y2: object, construction: object,
) -> SketchAddLineResult:
    request = build_sketch_add_line_request(doc_name, sketch_name, x1, y1, x2, y2, construction)
    if isinstance(request, dict):
        return request
    return _SketchAddLineExecution(collaborators, request).run()


class _SketchAddLineRpcFacade(Protocol):
    _cad_collaborators: SketchAddLineCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sketch_add_line(
    self: _SketchAddLineRpcFacade, doc_name: str, sketch_name: str, x1: float, y1: float, x2: float, y2: float, construction: bool = False,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_add_line(collaborators, doc_name, sketch_name, x1, y1, x2, y2, construction)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_add_line", rpc_sketch_add_line)


__all__ = [
    "SketchAddLineCollaborators",
    "SketchAddLineError",
    "apply_sketch_add_line",
    "build_sketch_add_line_request",
    "read_sketch_add_line_result",
    "rpc_sketch_add_line",
    "run_sketch_add_line",
    "TYPED_RPC_HANDLER",
]
