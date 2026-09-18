"""Typed ``sketch_edit_constraint`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

try:
    from ...._shared.protocol.sketch_edit_constraint_contract import (
        DocumentName,
        SketchEditConstraintCollaborators,
        SketchEditConstraintDocument,
        SketchEditConstraintFailure,
        SketchEditConstraintObject,
        SketchEditConstraintReadDocument,
        SketchEditConstraintResult,
        SketchName,
        make_sketch_edit_constraint_failure,
        make_sketch_edit_constraint_success,
        make_sketch_edit_constraint_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.sketch_edit_constraint_contract import (
        DocumentName,
        SketchEditConstraintCollaborators,
        SketchEditConstraintDocument,
        SketchEditConstraintFailure,
        SketchEditConstraintObject,
        SketchEditConstraintReadDocument,
        SketchEditConstraintResult,
        SketchName,
        make_sketch_edit_constraint_failure,
        make_sketch_edit_constraint_success,
        make_sketch_edit_constraint_uncertain,
    )
from .sketch_edit_constraint_mutation import (
    SketchEditConstraintError,
    run_sketch_edit_constraint_native_mutation,
)


@dataclass(frozen=True, slots=True)
class SketchEditConstraintReceipt:
    name: str
    sketch: SketchEditConstraintObject
    index: int
    constraint_name: str
    expected_value: float


@dataclass(frozen=True, slots=True)
class SketchEditConstraintInspection:
    name: SketchName
    index: int
    constraint_name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class _SketchEditConstraintRequest:
    doc_name: DocumentName
    sketch_name: SketchName
    value: float | None
    constraint_name: str | None
    index: int | None


def _failure(
    error: SketchEditConstraintError, *, retry_safe: bool = True
) -> SketchEditConstraintFailure:
    return make_sketch_edit_constraint_failure(error.code, str(error), retry_safe=retry_safe)


def _resolve_index(sketch: object, name: str | None, index: int | None) -> int:
    if name is not None:
        matches = [
            i
            for i, constraint in enumerate(getattr(sketch, "Constraints", []) or [])
            if getattr(constraint, "Name", "") == name
        ]
        if not matches:
            raise SketchEditConstraintError("CONSTRAINT_NOT_FOUND", f"Constraint name not found: {name}")
        if len(matches) > 1:
            raise SketchEditConstraintError(
                "CONSTRAINT_NAME_AMBIGUOUS",
                f"Constraint name is not unique: {name}",
            )
        return matches[0]
    if index is not None:
        constraints = list(getattr(sketch, "Constraints", []) or [])
        if index >= len(constraints):
            raise SketchEditConstraintError(
                "CONSTRAINT_INDEX_OUT_OF_RANGE",
                f"Constraint index out of range: {index}",
            )
        return index
    raise SketchEditConstraintError("INVALID_ARGUMENT", "Provide constraint name or index")


def _constraint_datum(sketch: object, index: int) -> float | None:
    get_datum = getattr(sketch, "getDatum", None)
    if callable(get_datum):
        try:
            return float(get_datum(index))
        except (AttributeError, TypeError, ValueError, RuntimeError):
            return None
    constraints = list(getattr(sketch, "Constraints", []) or [])
    if index >= len(constraints):
        return None
    value = getattr(constraints[index], "value", None)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def apply_sketch_edit_constraint(
    doc: SketchEditConstraintDocument,
    sketch_name: SketchName,
    value: float | None,
    constraint_name: str | None,
    index: int | None,
) -> SketchEditConstraintReceipt:
    """Edit a sketch constraint without recomputing or managing a transaction."""

    sketch = doc.getObject(sketch_name)
    if sketch is None:
        raise SketchEditConstraintError("SKETCH_NOT_FOUND", f"Sketch {sketch_name!r} not found")
    if value is None:
        raise SketchEditConstraintError("INVALID_ARGUMENT", "value is required")
    resolved = _resolve_index(sketch, constraint_name, index)
    set_datum = getattr(sketch, "setDatum", None)
    if not callable(set_datum):
        raise SketchEditConstraintError(
            "NOT_A_SKETCH",
            f"Object {sketch_name!r} is not an editable Sketcher sketch",
        )
    set_datum(resolved, float(value))
    constraints = list(getattr(sketch, "Constraints", []) or [])
    resolved_name = str(getattr(constraints[resolved], "Name", "") or "") if resolved < len(constraints) else ""
    return SketchEditConstraintReceipt(
        name=sketch.Name,
        sketch=sketch,
        index=resolved,
        constraint_name=resolved_name,
        expected_value=float(value),
    )


def read_sketch_edit_constraint_result(
    doc: SketchEditConstraintReadDocument, receipt: SketchEditConstraintReceipt
) -> SketchEditConstraintInspection:
    sketch = doc.getObject(receipt.name)
    if sketch is None:
        raise SketchEditConstraintError("CREATED_OBJECT_MISSING", f"Sketch is missing: {receipt.name!r}")
    if sketch is not receipt.sketch:
        raise SketchEditConstraintError(
            "CREATED_OBJECT_REPLACED",
            f"Sketch was replaced before commit: {receipt.name!r}",
        )
    actual = _constraint_datum(sketch, receipt.index)
    if actual is None or abs(actual - receipt.expected_value) > 1e-6:
        raise SketchEditConstraintError(
            "CONSTRAINT_DATUM_NOT_UPDATED",
            f"Constraint datum at index {receipt.index} was not updated on {receipt.name!r}",
        )
    return SketchEditConstraintInspection(
        name=SketchName(receipt.name),
        index=receipt.index,
        constraint_name=receipt.constraint_name,
    )


def build_sketch_edit_constraint_request(
    doc_name: object,
    sketch_name: object,
    value: object,
    name: object,
    index: object,
) -> _SketchEditConstraintRequest | SketchEditConstraintFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(
            SketchEditConstraintError("INVALID_ARGUMENT", "doc_name must be a nonempty string")
        )
    if not isinstance(sketch_name, str) or not sketch_name.strip():
        return _failure(
            SketchEditConstraintError("INVALID_ARGUMENT", "sketch_name must be a nonempty string")
        )
    if name is None and index is None:
        return _failure(
            SketchEditConstraintError("INVALID_ARGUMENT", "Provide constraint name or index")
        )
    if value is None:
        return _failure(SketchEditConstraintError("INVALID_ARGUMENT", "value is required"))
    if name is not None and (not isinstance(name, str) or not name.strip()):
        return _failure(
            SketchEditConstraintError("INVALID_ARGUMENT", "name must be a nonempty string")
        )
    if index is not None and (isinstance(index, bool) or not isinstance(index, int) or index < 0):
        return _failure(
            SketchEditConstraintError("INVALID_ARGUMENT", "index must be a non-negative integer")
        )
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _failure(SketchEditConstraintError("INVALID_ARGUMENT", "value must be a number"))
    return _SketchEditConstraintRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        value=float(value),
        constraint_name=name if isinstance(name, str) else None,
        index=index if isinstance(index, int) and not isinstance(index, bool) else None,
    )


@dataclass(slots=True)
class _SketchEditConstraintExecution:
    collaborators: SketchEditConstraintCollaborators
    request: _SketchEditConstraintRequest
    created: SketchEditConstraintReceipt | None = None
    inspected: SketchEditConstraintInspection | None = None

    def apply(self, doc: SketchEditConstraintDocument) -> None:
        self.created = apply_sketch_edit_constraint(
            doc,
            self.request.sketch_name,
            self.request.value,
            self.request.constraint_name,
            self.request.index,
        )

    def inspect(self, doc: SketchEditConstraintReadDocument) -> None:
        if self.created is None:
            raise SketchEditConstraintError(
                "INVALID_SKETCH_EDIT_CONSTRAINT_RESULT",
                "Constraint edit did not return an identity receipt",
            )
        self.inspected = read_sketch_edit_constraint_result(doc, self.created)

    def run(self) -> SketchEditConstraintResult:
        result = run_sketch_edit_constraint_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_edit_constraint_uncertain(
                "SKETCH_EDIT_CONSTRAINT_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected edit result",
                committed=True,
            )
        return make_sketch_edit_constraint_success(
            self.inspected.name, self.inspected.index, self.inspected.constraint_name
        )


def run_sketch_edit_constraint(
    collaborators: SketchEditConstraintCollaborators,
    doc_name: object,
    sketch_name: object,
    value: object = None,
    name: object = None,
    index: object = None,
) -> SketchEditConstraintResult:
    request = build_sketch_edit_constraint_request(doc_name, sketch_name, value, name, index)
    if isinstance(request, dict):
        return request
    return _SketchEditConstraintExecution(collaborators, request).run()


class _SketchEditConstraintRpcFacade(Protocol):
    _cad_collaborators: SketchEditConstraintCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sketch_edit_constraint(
    self: _SketchEditConstraintRpcFacade,
    doc_name: str,
    sketch_name: str,
    value: float | None = None,
    name: str | None = None,
    index: int | None = None,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_edit_constraint(collaborators, doc_name, sketch_name, value, name, index)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_edit_constraint", rpc_sketch_edit_constraint)


__all__ = [
    "SketchEditConstraintCollaborators",
    "SketchEditConstraintError",
    "SketchEditConstraintInspection",
    "SketchEditConstraintReceipt",
    "apply_sketch_edit_constraint",
    "build_sketch_edit_constraint_request",
    "read_sketch_edit_constraint_result",
    "rpc_sketch_edit_constraint",
    "run_sketch_edit_constraint",
    "TYPED_RPC_HANDLER",
]
