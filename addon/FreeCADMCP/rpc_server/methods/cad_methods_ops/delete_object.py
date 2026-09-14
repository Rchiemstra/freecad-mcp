"""Typed ``delete_object`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.delete_object_contract import (
    DeleteObjectCollaborators,
    DeleteObjectFailure,
    DeleteObjectRequest,
    DeleteObjectResult,
    DocumentName,
    ObjectName,
    make_delete_object_failure,
    make_delete_object_success,
    make_delete_object_uncertain,
)
from .delete_object_mutation import DeleteObjectError, run_delete_object_native_mutation
from .typed_rpc_document import get_object, remove_object


@dataclass(frozen=True, slots=True)
class DeleteObjectReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    deleted: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DeleteObjectInspection:
    """Read-only data captured after the native-owned recompute."""

    name: ObjectName
    deleted: list[str]


def _failure(error: DeleteObjectError, *, retry_safe: bool = True) -> DeleteObjectFailure:
    return make_delete_object_failure(
        error.code, str(error), retry_safe=retry_safe, diagnostics=error.diagnostics
    )


def _as_bool(value: object, *, default: bool = False) -> bool | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return None


def _dependents(root: object) -> list[object]:
    seen: set[int] = set()
    order: list[object] = []

    def walk(node: object) -> None:
        for child in getattr(node, "OutList", ()) or ():
            marker = id(child)
            if marker in seen:
                continue
            seen.add(marker)
            order.append(child)
            walk(child)

    walk(root)
    return order


def apply_delete_object(doc: object, request: DeleteObjectRequest) -> DeleteObjectReceipt:
    """Delete an object without recomputing or managing a transaction."""

    obj = get_object(doc, str(request.object_name))
    if obj is None:
        raise DeleteObjectError(
            "OBJECT_NOT_FOUND",
            f"Object not found: {request.object_name!r}",
        )
    dependents = _dependents(obj)
    dep_names = [
        str(getattr(item, "Name", ""))
        for item in dependents
        if isinstance(getattr(item, "Name", None), str)
    ]
    root_name = str(getattr(obj, "Name", request.object_name))
    if dep_names and not request.recursive and not request.force:
        raise DeleteObjectError(
            "DELETE_REFUSED",
            (
                f"Refused to delete {root_name}: it has {len(dep_names)} dependent "
                "object(s) that would be orphaned"
            ),
            diagnostics={
                "dependents": [
                    {
                        "name": str(getattr(item, "Name", "")),
                        "type": str(getattr(item, "TypeId", "")),
                    }
                    for item in dependents
                ]
            },
        )
    deleted: list[str] = []
    if request.recursive:
        for name in reversed(dep_names):
            if get_object(doc, name) is not None:
                remove_object(doc, name)
                deleted.append(name)
    if get_object(doc, root_name) is not None:
        remove_object(doc, root_name)
        deleted.append(root_name)
    return DeleteObjectReceipt(name=root_name, deleted=tuple(deleted))


def read_delete_object_result(
    doc: object, receipt: DeleteObjectReceipt
) -> DeleteObjectInspection:
    """Build the public result after the shared mutation recompute."""

    remaining = [name for name in receipt.deleted if get_object(doc, name) is not None]
    if remaining:
        raise DeleteObjectError(
            "DELETED_OBJECT_REMAINING",
            f"Deleted objects are still present: {remaining!r}",
        )
    return DeleteObjectInspection(name=ObjectName(receipt.name), deleted=list(receipt.deleted))


def build_delete_object_request(
    doc_name: object,
    obj_name: object,
    recursive: object = False,
    force: object = False,
) -> DeleteObjectRequest | DeleteObjectFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(DeleteObjectError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(obj_name, str) or not obj_name.strip():
        return _failure(DeleteObjectError("INVALID_ARGUMENT", "obj_name must be a nonempty string"))
    recursive_flag = _as_bool(recursive)
    force_flag = _as_bool(force)
    if recursive_flag is None or force_flag is None:
        return _failure(DeleteObjectError("INVALID_ARGUMENT", "recursive and force must be booleans"))
    return DeleteObjectRequest(
        doc_name=DocumentName(doc_name),
        object_name=ObjectName(obj_name),
        recursive=recursive_flag,
        force=force_flag,
    )


@dataclass(slots=True)
class _DeleteObjectExecution:
    collaborators: DeleteObjectCollaborators
    request: DeleteObjectRequest
    created: DeleteObjectReceipt | None = None
    inspected: DeleteObjectInspection | None = None

    def apply(self, doc: object) -> None:
        self.created = apply_delete_object(doc, self.request)

    def inspect(self, doc: object) -> None:
        if self.created is None:
            raise DeleteObjectError(
                "INVALID_DELETE_OBJECT_RESULT",
                "Object deletion did not return an identity receipt",
            )
        self.inspected = read_delete_object_result(doc, self.created)

    def run(self) -> DeleteObjectResult:
        result = run_delete_object_native_mutation(
            self.collaborators,
            str(self.request.doc_name),
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_delete_object_uncertain(
                "DELETE_OBJECT_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected delete result",
                committed=True,
            )
        return make_delete_object_success(self.inspected.name, self.inspected.deleted)


def run_delete_object(
    collaborators: DeleteObjectCollaborators,
    doc_name: object,
    obj_name: object,
    recursive: object = False,
    force: object = False,
) -> DeleteObjectResult:
    """Run object deletion through apply, recompute, inspection, and commit."""

    request = build_delete_object_request(doc_name, obj_name, recursive, force)
    if isinstance(request, dict):
        return request
    return _DeleteObjectExecution(collaborators, request).run()


class _DeleteObjectRpcFacade(Protocol):
    _cad_collaborators: DeleteObjectCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_delete_object(
    self: _DeleteObjectRpcFacade,
    doc_name: str,
    obj_name: str,
    recursive: object = False,
    force: object = False,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_delete_object(collaborators, doc_name, obj_name, recursive, force)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("delete_object", rpc_delete_object)


__all__ = [
    "DeleteObjectCollaborators",
    "DeleteObjectError",
    "DeleteObjectInspection",
    "DeleteObjectReceipt",
    "apply_delete_object",
    "build_delete_object_request",
    "read_delete_object_result",
    "rpc_delete_object",
    "run_delete_object",
    "TYPED_RPC_HANDLER",
]
