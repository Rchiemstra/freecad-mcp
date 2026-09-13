"""Typed ``sketch_delete_constraint`` mutation."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.sketch_delete_constraint_contract import (
    DocumentName,
    SketchDeleteConstraintCollaborators,
    SketchDeleteConstraintDocument,
    SketchDeleteConstraintFailure,
    SketchDeleteConstraintObject,
    SketchDeleteConstraintReadDocument,
    SketchDeleteConstraintResult,
    SketchName,
    make_sketch_delete_constraint_failure,
    make_sketch_delete_constraint_success,
    make_sketch_delete_constraint_uncertain,
)
from .sketch_delete_constraint_mutation import (
    SketchDeleteConstraintError,
    run_sketch_delete_constraint_native_mutation,
)


@dataclass(frozen=True, slots=True)
class SketchDeleteConstraintReceipt:
    name: str
    sketch: SketchDeleteConstraintObject
    deleted_count: int


@dataclass(frozen=True, slots=True)
class SketchDeleteConstraintInspection:
    name: SketchName
    deleted_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class _SketchDeleteConstraintRequest:
    doc_name: DocumentName
    sketch_name: SketchName
    constraint_indices: tuple[int, ...]
    constraint_names: tuple[str, ...]


def _failure(
    error: SketchDeleteConstraintError, *, retry_safe: bool = True
) -> SketchDeleteConstraintFailure:
    return make_sketch_delete_constraint_failure(error.code, str(error), retry_safe=retry_safe)


def _resolve_indices(sketch: object, indices: Sequence[int], names: Sequence[str]) -> list[int]:
    constraints = list(getattr(sketch, "Constraints", []) or [])
    invalid = sorted({index for index in indices if index >= len(constraints)})
    if invalid:
        raise SketchDeleteConstraintError(
            "CONSTRAINT_INDEX_OUT_OF_RANGE",
            "Constraint index out of range: " + ", ".join(str(index) for index in invalid),
        )
    resolved = set(indices)
    for name in names:
        matches = [
            index
            for index, constraint in enumerate(constraints)
            if getattr(constraint, "Name", "") == name
        ]
        if not matches:
            raise SketchDeleteConstraintError(
                "CONSTRAINT_NOT_FOUND",
                f"Constraint name not found: {name}",
            )
        if len(matches) > 1:
            raise SketchDeleteConstraintError(
                "CONSTRAINT_NAME_AMBIGUOUS",
                f"Constraint name is not unique: {name}",
            )
        resolved.add(matches[0])
    return sorted(resolved)


def apply_sketch_delete_constraint(
    doc: SketchDeleteConstraintDocument,
    sketch_name: SketchName,
    constraint_indices: Sequence[int],
    constraint_names: Sequence[str],
) -> SketchDeleteConstraintReceipt:
    """Delete sketch constraints without recomputing or managing a transaction."""

    sketch = doc.getObject(sketch_name)
    if sketch is None:
        raise SketchDeleteConstraintError("SKETCH_NOT_FOUND", f"Sketch {sketch_name!r} not found")
    delete = getattr(sketch, "delConstraints", None)
    if not callable(delete):
        raise SketchDeleteConstraintError(
            "NOT_A_SKETCH",
            f"Object {sketch_name!r} is not an editable Sketcher sketch",
        )
    target = _resolve_indices(sketch, constraint_indices, constraint_names)
    delete(target, True)
    return SketchDeleteConstraintReceipt(name=sketch.Name, sketch=sketch, deleted_count=len(target))


def read_sketch_delete_constraint_result(
    doc: SketchDeleteConstraintReadDocument, receipt: SketchDeleteConstraintReceipt
) -> SketchDeleteConstraintInspection:
    sketch = doc.getObject(receipt.name)
    if sketch is None:
        raise SketchDeleteConstraintError("CREATED_OBJECT_MISSING", f"Sketch is missing: {receipt.name!r}")
    if sketch is not receipt.sketch:
        raise SketchDeleteConstraintError(
            "CREATED_OBJECT_REPLACED",
            f"Sketch was replaced before commit: {receipt.name!r}",
        )
    return SketchDeleteConstraintInspection(
        name=SketchName(receipt.name), deleted_count=receipt.deleted_count
    )


def build_sketch_delete_constraint_request(
    doc_name: object,
    sketch_name: object,
    constraint_indices: object,
    constraint_names: object,
) -> _SketchDeleteConstraintRequest | SketchDeleteConstraintFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(
            SketchDeleteConstraintError("INVALID_ARGUMENT", "doc_name must be a nonempty string")
        )
    if not isinstance(sketch_name, str) or not sketch_name.strip():
        return _failure(
            SketchDeleteConstraintError("INVALID_ARGUMENT", "sketch_name must be a nonempty string")
        )
    indices_raw = [] if constraint_indices is None else constraint_indices
    names_raw = [] if constraint_names is None else constraint_names
    if not isinstance(indices_raw, list) or not isinstance(names_raw, list):
        return _failure(
            SketchDeleteConstraintError(
                "INVALID_ARGUMENT",
                "constraint_indices and constraint_names must be lists",
            )
        )
    if not indices_raw and not names_raw:
        return _failure(
            SketchDeleteConstraintError(
                "INVALID_ARGUMENT",
                "Provide at least one constraint index or name",
            )
        )
    indices: list[int] = []
    for index in indices_raw:
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            return _failure(
                SketchDeleteConstraintError(
                    "INVALID_ARGUMENT",
                    "constraint_indices must contain non-negative integers",
                )
            )
        indices.append(index)
    names: list[str] = []
    for name in names_raw:
        if not isinstance(name, str) or not name:
            return _failure(
                SketchDeleteConstraintError(
                    "INVALID_ARGUMENT",
                    "constraint_names must contain non-empty strings",
                )
            )
        names.append(name)
    return _SketchDeleteConstraintRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        constraint_indices=tuple(indices),
        constraint_names=tuple(names),
    )


@dataclass(slots=True)
class _SketchDeleteConstraintExecution:
    collaborators: SketchDeleteConstraintCollaborators
    request: _SketchDeleteConstraintRequest
    created: SketchDeleteConstraintReceipt | None = None
    inspected: SketchDeleteConstraintInspection | None = None

    def apply(self, doc: SketchDeleteConstraintDocument) -> None:
        self.created = apply_sketch_delete_constraint(
            doc,
            self.request.sketch_name,
            self.request.constraint_indices,
            self.request.constraint_names,
        )

    def inspect(self, doc: SketchDeleteConstraintReadDocument) -> None:
        if self.created is None:
            raise SketchDeleteConstraintError(
                "INVALID_SKETCH_DELETE_CONSTRAINT_RESULT",
                "Constraint delete did not return an identity receipt",
            )
        self.inspected = read_sketch_delete_constraint_result(doc, self.created)

    def run(self) -> SketchDeleteConstraintResult:
        result = run_sketch_delete_constraint_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_delete_constraint_uncertain(
                "SKETCH_DELETE_CONSTRAINT_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected delete result",
                committed=True,
            )
        return make_sketch_delete_constraint_success(
            self.inspected.name, self.inspected.deleted_count
        )


def run_sketch_delete_constraint(
    collaborators: SketchDeleteConstraintCollaborators,
    doc_name: object,
    sketch_name: object,
    constraint_indices: object = None,
    constraint_names: object = None,
) -> SketchDeleteConstraintResult:
    request = build_sketch_delete_constraint_request(
        doc_name, sketch_name, constraint_indices, constraint_names
    )
    if isinstance(request, dict):
        return request
    return _SketchDeleteConstraintExecution(collaborators, request).run()


class _SketchDeleteConstraintRpcFacade(Protocol):
    _cad_collaborators: SketchDeleteConstraintCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sketch_delete_constraint(
    self: _SketchDeleteConstraintRpcFacade,
    doc_name: str,
    sketch_name: str,
    constraint_indices: object = None,
    constraint_names: object = None,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_delete_constraint(
            collaborators, doc_name, sketch_name, constraint_indices, constraint_names
        )
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_delete_constraint", rpc_sketch_delete_constraint)


__all__ = [
    "SketchDeleteConstraintCollaborators",
    "SketchDeleteConstraintError",
    "SketchDeleteConstraintInspection",
    "SketchDeleteConstraintReceipt",
    "apply_sketch_delete_constraint",
    "build_sketch_delete_constraint_request",
    "read_sketch_delete_constraint_result",
    "rpc_sketch_delete_constraint",
    "run_sketch_delete_constraint",
    "TYPED_RPC_HANDLER",
]
