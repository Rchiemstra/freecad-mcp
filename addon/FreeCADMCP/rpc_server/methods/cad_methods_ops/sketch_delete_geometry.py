"""Typed ``sketch_delete_geometry`` mutation."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

try:
    from ...._shared.protocol.sketch_delete_geometry_contract import (
        DocumentName,
        SketchDeleteGeometryCollaborators,
        SketchDeleteGeometryDocument,
        SketchDeleteGeometryFailure,
        SketchDeleteGeometryObject,
        SketchDeleteGeometryReadDocument,
        SketchDeleteGeometryResult,
        SketchName,
        make_sketch_delete_geometry_failure,
        make_sketch_delete_geometry_success,
        make_sketch_delete_geometry_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.sketch_delete_geometry_contract import (
        DocumentName,
        SketchDeleteGeometryCollaborators,
        SketchDeleteGeometryDocument,
        SketchDeleteGeometryFailure,
        SketchDeleteGeometryObject,
        SketchDeleteGeometryReadDocument,
        SketchDeleteGeometryResult,
        SketchName,
        make_sketch_delete_geometry_failure,
        make_sketch_delete_geometry_success,
        make_sketch_delete_geometry_uncertain,
    )
from .sketch_delete_geometry_mutation import (
    SketchDeleteGeometryError,
    run_sketch_delete_geometry_native_mutation,
)


@dataclass(frozen=True, slots=True)
class SketchDeleteGeometryReceipt:
    name: str
    sketch: SketchDeleteGeometryObject
    deleted_count: int
    geometry_count_before: int


@dataclass(frozen=True, slots=True)
class SketchDeleteGeometryInspection:
    name: SketchName
    deleted_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class _SketchDeleteGeometryRequest:
    doc_name: DocumentName
    sketch_name: SketchName
    geometry_indices: tuple[int, ...]


def _failure(
    error: SketchDeleteGeometryError, *, retry_safe: bool = True
) -> SketchDeleteGeometryFailure:
    return make_sketch_delete_geometry_failure(error.code, str(error), retry_safe=retry_safe)


def _geometry_count(sketch: object) -> int:
    count = getattr(sketch, "GeometryCount", None)
    if isinstance(count, int) and not isinstance(count, bool):
        return count
    return len(getattr(sketch, "Geometry", []) or [])


def apply_sketch_delete_geometry(
    doc: SketchDeleteGeometryDocument,
    sketch_name: SketchName,
    geometry_indices: Sequence[int],
) -> SketchDeleteGeometryReceipt:
    """Delete sketch geometry without recomputing or managing a transaction."""

    sketch = doc.getObject(sketch_name)
    if sketch is None:
        raise SketchDeleteGeometryError("SKETCH_NOT_FOUND", f"Sketch {sketch_name!r} not found")
    delete = getattr(sketch, "delGeometries", None)
    if not callable(delete):
        raise SketchDeleteGeometryError(
            "NOT_A_SKETCH",
            f"Object {sketch_name!r} is not an editable Sketcher sketch",
        )
    geometry = list(getattr(sketch, "Geometry", []) or [])
    invalid = sorted({index for index in geometry_indices if index >= len(geometry)})
    if invalid:
        raise SketchDeleteGeometryError(
            "GEOMETRY_INDEX_OUT_OF_RANGE",
            "Geometry index out of range: " + ", ".join(str(index) for index in invalid),
        )
    target = sorted(set(geometry_indices))
    geometry_count_before = _geometry_count(sketch)
    delete(target)
    return SketchDeleteGeometryReceipt(
        name=sketch.Name,
        sketch=sketch,
        deleted_count=len(target),
        geometry_count_before=geometry_count_before,
    )


def read_sketch_delete_geometry_result(
    doc: SketchDeleteGeometryReadDocument, receipt: SketchDeleteGeometryReceipt
) -> SketchDeleteGeometryInspection:
    sketch = doc.getObject(receipt.name)
    if sketch is None:
        raise SketchDeleteGeometryError("CREATED_OBJECT_MISSING", f"Sketch is missing: {receipt.name!r}")
    if sketch is not receipt.sketch:
        raise SketchDeleteGeometryError(
            "CREATED_OBJECT_REPLACED",
            f"Sketch was replaced before commit: {receipt.name!r}",
        )
    expected = receipt.geometry_count_before - receipt.deleted_count
    if _geometry_count(sketch) != expected:
        raise SketchDeleteGeometryError(
            "GEOMETRY_NOT_DELETED",
            f"Sketch geometry count did not decrease on {receipt.name!r}",
        )
    return SketchDeleteGeometryInspection(
        name=SketchName(receipt.name), deleted_count=receipt.deleted_count
    )


def build_sketch_delete_geometry_request(
    doc_name: object, sketch_name: object, geometry_indices: object
) -> _SketchDeleteGeometryRequest | SketchDeleteGeometryFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(
            SketchDeleteGeometryError("INVALID_ARGUMENT", "doc_name must be a nonempty string")
        )
    if not isinstance(sketch_name, str) or not sketch_name.strip():
        return _failure(
            SketchDeleteGeometryError("INVALID_ARGUMENT", "sketch_name must be a nonempty string")
        )
    if not isinstance(geometry_indices, list) or not geometry_indices:
        return _failure(
            SketchDeleteGeometryError("INVALID_ARGUMENT", "geometry_indices must be a non-empty list")
        )
    indices: list[int] = []
    for index in geometry_indices:
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            return _failure(
                SketchDeleteGeometryError(
                    "INVALID_ARGUMENT",
                    "geometry_indices must contain non-negative integers",
                )
            )
        indices.append(index)
    return _SketchDeleteGeometryRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        geometry_indices=tuple(indices),
    )


@dataclass(slots=True)
class _SketchDeleteGeometryExecution:
    collaborators: SketchDeleteGeometryCollaborators
    request: _SketchDeleteGeometryRequest
    created: SketchDeleteGeometryReceipt | None = None
    inspected: SketchDeleteGeometryInspection | None = None

    def apply(self, doc: SketchDeleteGeometryDocument) -> None:
        self.created = apply_sketch_delete_geometry(
            doc, self.request.sketch_name, self.request.geometry_indices
        )

    def inspect(self, doc: SketchDeleteGeometryReadDocument) -> None:
        if self.created is None:
            raise SketchDeleteGeometryError(
                "INVALID_SKETCH_DELETE_GEOMETRY_RESULT",
                "Geometry delete did not return an identity receipt",
            )
        self.inspected = read_sketch_delete_geometry_result(doc, self.created)

    def run(self) -> SketchDeleteGeometryResult:
        result = run_sketch_delete_geometry_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_delete_geometry_uncertain(
                "SKETCH_DELETE_GEOMETRY_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected delete result",
                committed=True,
            )
        return make_sketch_delete_geometry_success(
            self.inspected.name, self.inspected.deleted_count
        )


def run_sketch_delete_geometry(
    collaborators: SketchDeleteGeometryCollaborators,
    doc_name: object,
    sketch_name: object,
    geometry_indices: object,
) -> SketchDeleteGeometryResult:
    request = build_sketch_delete_geometry_request(doc_name, sketch_name, geometry_indices)
    if isinstance(request, dict):
        return request
    return _SketchDeleteGeometryExecution(collaborators, request).run()


class _SketchDeleteGeometryRpcFacade(Protocol):
    _cad_collaborators: SketchDeleteGeometryCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sketch_delete_geometry(
    self: _SketchDeleteGeometryRpcFacade,
    doc_name: str,
    sketch_name: str,
    geometry_indices: object,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_delete_geometry(collaborators, doc_name, sketch_name, geometry_indices)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_delete_geometry", rpc_sketch_delete_geometry)


__all__ = [
    "SketchDeleteGeometryCollaborators",
    "SketchDeleteGeometryError",
    "SketchDeleteGeometryInspection",
    "SketchDeleteGeometryReceipt",
    "apply_sketch_delete_geometry",
    "build_sketch_delete_geometry_request",
    "read_sketch_delete_geometry_result",
    "rpc_sketch_delete_geometry",
    "run_sketch_delete_geometry",
    "TYPED_RPC_HANDLER",
]
