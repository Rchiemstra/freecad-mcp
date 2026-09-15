
"""Typed ``move_object`` mutation."""
from __future__ import annotations

from .typed_rpc_support import (
    as_bool,
    nonempty_string,
    object_label,
    object_name,
    require_object,
)
from .typed_rpc_container_support import (
    add_to_container,
    remove_from_container,
)

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.move_object_contract import (
    MoveObjectCollaborators,
    MoveObjectDocument,
    MoveObjectFailure,
    MoveObjectName,
    MoveObjectReadDocument,
    MoveObjectRequest,
    MoveObjectResult,
    DocumentName,
    make_move_object_failure,
    make_move_object_success,
    make_move_object_uncertain,
)
from .move_object_mutation import MoveObjectError, run_move_object_native_mutation



@dataclass(frozen=True, slots=True)
class MoveObjectReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    skipped: bool = False
    extra: object = None


@dataclass(frozen=True, slots=True)
class MoveObjectInspection:
    """Read-only data captured after the native-owned recompute."""

    name: MoveObjectName
    label: str
    extra: object = None


def _failure(error: MoveObjectError, *, retry_safe: bool = True) -> MoveObjectFailure:
    return make_move_object_failure(error.code, str(error), retry_safe=retry_safe)


def _object_in_owner(located: object, owner: object) -> bool:
    group = list(getattr(owner, "Group", None) or [])
    if located in group:
        return True
    in_list = list(getattr(located, "InList", None) or [])
    return owner in in_list


def apply_move_object(doc: MoveObjectDocument, request: MoveObjectRequest) -> MoveObjectReceipt:
    """Move an object into a container without recomputing."""

    if request.obj_name == request.target_container:
        raise MoveObjectError("INVALID_ARGUMENT", "obj_name and target_container must differ")
    item = require_object(doc, request.obj_name, missing_code="OBJECT_NOT_FOUND", error=MoveObjectError)
    target = require_object(doc, request.target_container, missing_code="OBJECT_NOT_FOUND", error=MoveObjectError)
    if request.remove_from_old_parent:
        for parent in list(getattr(item, "InList", []) or []):
            group = getattr(parent, "Group", None)
            if isinstance(group, (list, tuple)) and item in group:
                remove_from_container(parent, item)
    add_to_container(target, item)
    return MoveObjectReceipt(
        name=object_name(item) or request.obj_name,
        item=item,
        skipped=False,
        extra={"target_container": request.target_container},
    )


def read_move_object_result(doc: MoveObjectReadDocument, receipt: MoveObjectReceipt) -> MoveObjectInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        raise MoveObjectError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if receipt.item is not None and located is not receipt.item:
        raise MoveObjectError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")

    target_name = None
    if isinstance(receipt.extra, dict):
        target_name = receipt.extra.get("target_container")
    if target_name:
        target = doc.getObject(str(target_name))
        if target is None:
            raise MoveObjectError("MOVE_FAILED", f"Target container is missing: {target_name!r}")
        if not _object_in_owner(located, target):
            raise MoveObjectError(
                "POSTCONDITION_FAILED",
                f"Object is not grouped under target container: {target_name!r}",
            )

    return MoveObjectInspection(
        name=MoveObjectName(receipt.name),
        label=object_label(located),
        extra=receipt.extra,
    )


def build_move_object_request(doc_name: object, obj_name: object, target_container: object, remove_from_old_parent: object) -> MoveObjectRequest | MoveObjectFailure:
    doc_name_value = nonempty_string(doc_name, "doc_name")
    if doc_name_value is None:
        return _failure(MoveObjectError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    obj_name_value = nonempty_string(obj_name, "obj_name")
    if obj_name_value is None:
        return _failure(MoveObjectError("INVALID_ARGUMENT", "obj_name must be a nonempty string"))
    target_container_value = nonempty_string(target_container, "target_container")
    if target_container_value is None:
        return _failure(MoveObjectError("INVALID_ARGUMENT", "target_container must be a nonempty string"))
    remove_from_old_parent_value = as_bool(remove_from_old_parent, True)
    if remove_from_old_parent_value is None:
        return _failure(MoveObjectError("INVALID_ARGUMENT", "remove_from_old_parent must be a boolean"))
    return MoveObjectRequest(
        doc_name=DocumentName(doc_name_value),
        obj_name=obj_name_value,
        target_container=target_container_value,
        remove_from_old_parent=remove_from_old_parent_value,
    )


@dataclass(slots=True)
class _MoveObjectExecution:
    collaborators: MoveObjectCollaborators
    request: MoveObjectRequest
    created: MoveObjectReceipt | None = None
    inspected: MoveObjectInspection | None = None

    def apply(self, doc: MoveObjectDocument) -> None:
        self.created = apply_move_object(doc, self.request)

    def inspect(self, doc: MoveObjectReadDocument) -> None:
        if self.created is None:
            raise MoveObjectError(
                "INVALID_MOVE_OBJECT_RESULT",
                "move_object did not return an identity receipt",
            )
        self.inspected = read_move_object_result(doc, self.created)

    def run(self) -> MoveObjectResult:
        result = run_move_object_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_move_object_uncertain(
                "MOVE_OBJECT_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        return make_move_object_success(object_name=self.inspected.name, target_container=self.request.target_container)


def run_move_object(
    collaborators: MoveObjectCollaborators,
    doc_name: object, obj_name: object, target_container: object, remove_from_old_parent: object,
) -> MoveObjectResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_move_object_request(doc_name, obj_name, target_container, remove_from_old_parent)
    if isinstance(request, dict):
        return request
    return _MoveObjectExecution(collaborators, request).run()


class _MoveObjectRpcFacade(Protocol):
    _cad_collaborators: MoveObjectCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_move_object(
    self: _MoveObjectRpcFacade, doc_name: str, obj_name: str, target_container: str, remove_from_old_parent: bool = True,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_move_object(collaborators, doc_name, obj_name, target_container, remove_from_old_parent)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("move_object", rpc_move_object)


__all__ = [
    "MoveObjectCollaborators",
    "MoveObjectError",
    "MoveObjectInspection",
    "MoveObjectReceipt",
    "apply_move_object",
    "build_move_object_request",
    "read_move_object_result",
    "rpc_move_object",
    "run_move_object",
    "TYPED_RPC_HANDLER",
]
