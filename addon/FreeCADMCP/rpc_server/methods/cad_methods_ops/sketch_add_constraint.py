"""Typed ``sketch_add_constraint`` mutation."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

try:
    from ...._shared.protocol.sketch_add_constraint_contract import (
        DocumentName,
        SketchAddConstraintCollaborators,
        SketchAddConstraintDocument,
        SketchAddConstraintFailure,
        SketchAddConstraintObject,
        SketchAddConstraintReadDocument,
        SketchAddConstraintResult,
        SketchName,
        make_sketch_add_constraint_failure,
        make_sketch_add_constraint_success,
        make_sketch_add_constraint_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.sketch_add_constraint_contract import (
        DocumentName,
        SketchAddConstraintCollaborators,
        SketchAddConstraintDocument,
        SketchAddConstraintFailure,
        SketchAddConstraintObject,
        SketchAddConstraintReadDocument,
        SketchAddConstraintResult,
        SketchName,
        make_sketch_add_constraint_failure,
        make_sketch_add_constraint_success,
        make_sketch_add_constraint_uncertain,
    )
from .sketch_add_constraint_mutation import (
    SketchAddConstraintError,
    run_sketch_add_constraint_native_mutation,
)


@dataclass(frozen=True, slots=True)
class SketchAddConstraintReceipt:
    name: str
    sketch: SketchAddConstraintObject
    added_count: int
    constraint_count_before: int


@dataclass(frozen=True, slots=True)
class SketchAddConstraintInspection:
    name: SketchName
    added_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class _SketchAddConstraintRequest:
    doc_name: DocumentName
    sketch_name: SketchName
    constraints: tuple[Mapping[str, object], ...]


def _failure(
    error: SketchAddConstraintError, *, retry_safe: bool = True
) -> SketchAddConstraintFailure:
    return make_sketch_add_constraint_failure(error.code, str(error), retry_safe=retry_safe)


def _constraint_count(sketch: object) -> int:
    count = getattr(sketch, "ConstraintCount", None)
    if isinstance(count, int) and not isinstance(count, bool):
        return count
    return len(getattr(sketch, "Constraints", []) or [])


def _int_field(data: Mapping[str, object], key: str, default: int | None = None) -> int:
    if key not in data:
        if default is not None:
            return default
        raise SketchAddConstraintError("INVALID_ARGUMENT", f"{key} is required")
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise SketchAddConstraintError("INVALID_ARGUMENT", f"{key} must be an integer")
    return value


def _float_field(data: Mapping[str, object], key: str) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SketchAddConstraintError("INVALID_ARGUMENT", f"{key} must be a number")
    return float(value)


def _constraint_args(constraint: Mapping[str, object]) -> tuple[object, ...]:
    ctype_obj = constraint.get("type", "")
    ctype = ctype_obj if isinstance(ctype_obj, str) else ""
    if ctype == "Coincident":
        return (
            "Coincident",
            _int_field(constraint, "geo1"),
            _int_field(constraint, "pos1"),
            _int_field(constraint, "geo2"),
            _int_field(constraint, "pos2"),
        )
    if ctype == "Horizontal":
        return ("Horizontal", _int_field(constraint, "geo"))
    if ctype == "Vertical":
        return ("Vertical", _int_field(constraint, "geo"))
    if ctype == "Radius":
        return ("Radius", _int_field(constraint, "geo"), _float_field(constraint, "value"))
    if ctype == "Diameter":
        return ("Diameter", _int_field(constraint, "geo"), _float_field(constraint, "value"))
    if ctype == "Parallel":
        return ("Parallel", _int_field(constraint, "geo1"), _int_field(constraint, "geo2"))
    if ctype == "Perpendicular":
        return ("Perpendicular", _int_field(constraint, "geo1"), _int_field(constraint, "geo2"))
    if ctype == "Equal":
        return ("Equal", _int_field(constraint, "geo1"), _int_field(constraint, "geo2"))
    if ctype == "Tangent":
        return ("Tangent", _int_field(constraint, "geo1"), _int_field(constraint, "geo2"))
    if ctype == "Block":
        return ("Block", _int_field(constraint, "geo"))
    if ctype == "PointOnObject":
        return (
            "PointOnObject",
            _int_field(constraint, "geo1"),
            _int_field(constraint, "pos1"),
            _int_field(constraint, "geo2"),
        )
    if ctype == "Symmetric":
        return (
            "Symmetric",
            _int_field(constraint, "geo1"),
            _int_field(constraint, "pos1"),
            _int_field(constraint, "geo2"),
            _int_field(constraint, "pos2"),
            _int_field(constraint, "geo3"),
            _int_field(constraint, "pos3", 0),
        )
    if ctype == "Distance":
        if "geo2" in constraint:
            return (
                "Distance",
                _int_field(constraint, "geo1"),
                _int_field(constraint, "pos1", 0),
                _int_field(constraint, "geo2"),
                _int_field(constraint, "pos2", 0),
                _float_field(constraint, "value"),
            )
        if "pos" in constraint:
            return (
                "Distance",
                _int_field(constraint, "geo"),
                _int_field(constraint, "pos"),
                _float_field(constraint, "value"),
            )
        return ("Distance", _int_field(constraint, "geo"), _float_field(constraint, "value"))
    if ctype in {"DistanceX", "DistanceY"}:
        if "pos" in constraint:
            return (
                ctype,
                _int_field(constraint, "geo"),
                _int_field(constraint, "pos"),
                _float_field(constraint, "value"),
            )
        return (ctype, _int_field(constraint, "geo"), _float_field(constraint, "value"))
    if ctype == "Angle":
        if "geo2" in constraint:
            return (
                "Angle",
                _int_field(constraint, "geo1"),
                _int_field(constraint, "pos1", 0),
                _int_field(constraint, "geo2"),
                _int_field(constraint, "pos2", 0),
                _float_field(constraint, "value"),
            )
        return ("Angle", _int_field(constraint, "geo"), _float_field(constraint, "value"))
    raise SketchAddConstraintError("INVALID_ARGUMENT", f"Unknown constraint type: {ctype!r}")


def apply_sketch_add_constraint(
    doc: SketchAddConstraintDocument,
    sketch_name: SketchName,
    constraints: Sequence[Mapping[str, object]],
    collaborators: SketchAddConstraintCollaborators,
) -> SketchAddConstraintReceipt:
    """Add sketch constraints without recomputing or managing a transaction."""

    sketch = doc.getObject(sketch_name)
    if sketch is None:
        raise SketchAddConstraintError("SKETCH_NOT_FOUND", f"Sketch {sketch_name!r} not found")
    add_constraint = getattr(sketch, "addConstraint", None)
    if not callable(add_constraint):
        raise SketchAddConstraintError("NOT_A_SKETCH", f"Object {sketch_name!r} is not an editable sketch")
    constraint_count_before = _constraint_count(sketch)
    constraint_type = getattr(collaborators.sketcher, "Constraint")
    added = 0
    for constraint in constraints:
        idx = add_constraint(constraint_type(*_constraint_args(constraint)))
        name = constraint.get("name")
        if isinstance(name, str) and name and idx is not None:
            rename = getattr(sketch, "renameConstraint", None)
            if callable(rename):
                rename(idx, name)
        added += 1
    return SketchAddConstraintReceipt(
        name=sketch.Name,
        sketch=sketch,
        added_count=added,
        constraint_count_before=constraint_count_before,
    )


def read_sketch_add_constraint_result(
    doc: SketchAddConstraintReadDocument, receipt: SketchAddConstraintReceipt
) -> SketchAddConstraintInspection:
    sketch = doc.getObject(receipt.name)
    if sketch is None:
        raise SketchAddConstraintError("CREATED_OBJECT_MISSING", f"Sketch is missing: {receipt.name!r}")
    if sketch is not receipt.sketch:
        raise SketchAddConstraintError(
            "CREATED_OBJECT_REPLACED",
            f"Sketch was replaced before commit: {receipt.name!r}",
        )
    if _constraint_count(sketch) < receipt.constraint_count_before + receipt.added_count:
        raise SketchAddConstraintError(
            "CONSTRAINT_NOT_ADDED",
            f"Sketch constraint count did not increase on {receipt.name!r}",
        )
    return SketchAddConstraintInspection(name=SketchName(receipt.name), added_count=receipt.added_count)


def build_sketch_add_constraint_request(
    doc_name: object, sketch_name: object, constraints: object
) -> _SketchAddConstraintRequest | SketchAddConstraintFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(SketchAddConstraintError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(sketch_name, str) or not sketch_name.strip():
        return _failure(
            SketchAddConstraintError("INVALID_ARGUMENT", "sketch_name must be a nonempty string")
        )
    if not isinstance(constraints, list) or not constraints:
        return _failure(
            SketchAddConstraintError("INVALID_ARGUMENT", "constraints must be a non-empty list")
        )
    items: list[Mapping[str, object]] = []
    for item in constraints:
        if not isinstance(item, Mapping) or any(not isinstance(key, str) for key in item):
            return _failure(
                SketchAddConstraintError("INVALID_ARGUMENT", "constraints items must be objects")
            )
        items.append({str(key): item[key] for key in item})
    return _SketchAddConstraintRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        constraints=tuple(items),
    )


@dataclass(slots=True)
class _SketchAddConstraintExecution:
    collaborators: SketchAddConstraintCollaborators
    request: _SketchAddConstraintRequest
    created: SketchAddConstraintReceipt | None = None
    inspected: SketchAddConstraintInspection | None = None

    def apply(self, doc: SketchAddConstraintDocument) -> None:
        self.created = apply_sketch_add_constraint(
            doc, self.request.sketch_name, self.request.constraints, self.collaborators
        )

    def inspect(self, doc: SketchAddConstraintReadDocument) -> None:
        if self.created is None:
            raise SketchAddConstraintError(
                "INVALID_SKETCH_ADD_CONSTRAINT_RESULT",
                "Constraint add did not return an identity receipt",
            )
        self.inspected = read_sketch_add_constraint_result(doc, self.created)

    def run(self) -> SketchAddConstraintResult:
        result = run_sketch_add_constraint_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_add_constraint_uncertain(
                "SKETCH_ADD_CONSTRAINT_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected constraint result",
                committed=True,
            )
        return make_sketch_add_constraint_success(self.inspected.name, self.inspected.added_count)


def run_sketch_add_constraint(
    collaborators: SketchAddConstraintCollaborators,
    doc_name: object,
    sketch_name: object,
    constraints: object,
) -> SketchAddConstraintResult:
    request = build_sketch_add_constraint_request(doc_name, sketch_name, constraints)
    if isinstance(request, dict):
        return request
    return _SketchAddConstraintExecution(collaborators, request).run()


class _SketchAddConstraintRpcFacade(Protocol):
    _cad_collaborators: SketchAddConstraintCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sketch_add_constraint(
    self: _SketchAddConstraintRpcFacade,
    doc_name: str,
    sketch_name: str,
    constraints: object,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_add_constraint(collaborators, doc_name, sketch_name, constraints)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_add_constraint", rpc_sketch_add_constraint)


__all__ = [
    "SketchAddConstraintCollaborators",
    "SketchAddConstraintError",
    "SketchAddConstraintInspection",
    "SketchAddConstraintReceipt",
    "apply_sketch_add_constraint",
    "build_sketch_add_constraint_request",
    "read_sketch_add_constraint_result",
    "rpc_sketch_add_constraint",
    "run_sketch_add_constraint",
    "TYPED_RPC_HANDLER",
]
