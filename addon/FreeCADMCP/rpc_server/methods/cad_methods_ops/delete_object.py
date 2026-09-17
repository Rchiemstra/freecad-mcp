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
    refused: bool = False
    dependents: tuple[object, ...] = ()


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


def _links(item: object, attribute: str) -> tuple[object, ...]:
    raw = getattr(item, attribute, ()) or ()
    if isinstance(raw, (list, tuple)):
        return tuple(raw)
    return ()


def _is_derived(item: object, type_id: str) -> bool:
    derived = getattr(item, "isDerivedFrom", None)
    if callable(derived):
        try:
            return bool(derived(type_id))
        except Exception:
            pass
    return str(getattr(item, "TypeId", "")) == type_id


def _owns(container: object, item: object) -> bool:
    return any(member is item for member in _links(container, "Group"))


def _owning_container(item: object) -> object | None:
    getter = getattr(item, "getParentGeoFeatureGroup", None)
    if callable(getter):
        try:
            owner: object | None = getter()
        except Exception:
            owner = None
        if owner is not None and _owns(owner, item):
            return owner
    for candidate in _links(item, "InList"):
        if _owns(candidate, item):
            return candidate
    return None


def _ownership_exclusions(container: object | None) -> set[int]:
    excluded: set[int] = set()

    def mark(item: object) -> None:
        identity = id(item)
        if identity in excluded:
            return
        excluded.add(identity)
        for child in _links(item, "OutList"):
            mark(child)

    origin = getattr(container, "Origin", None) if container is not None else None
    if origin is not None:
        mark(origin)
    return excluded


def _object_dependents(root: object) -> list[object]:
    owner = _owning_container(root)
    root_is_container = (
        _is_derived(root, "PartDesign::Body")
        or _is_derived(root, "App::DocumentObjectGroup")
        or _is_derived(root, "App::Part")
    )
    excluded = _ownership_exclusions(root if root_is_container else owner)
    if owner is not None:
        excluded.add(id(owner))
    seen = {id(root), *excluded}
    ordered: list[object] = []

    def visit_downstream(item: object, allowed: set[int] | None = None) -> None:
        identity = id(item)
        if identity in seen:
            return
        seen.add(identity)
        for dependent in _links(item, "InList"):
            dependent_id = id(dependent)
            if dependent_id in seen or (allowed is not None and dependent_id not in allowed):
                continue
            if _owns(dependent, item):
                seen.add(dependent_id)
                continue
            visit_downstream(dependent, allowed)
        if item is not root:
            ordered.append(item)

    if root_is_container:
        payload = _links(root, "Group") or _links(root, "OutList")
        payload = tuple(item for item in payload if id(item) not in excluded)
        allowed = {id(item) for item in payload}
        for item in payload:
            visit_downstream(item, allowed)
    else:
        seen.remove(id(root))
        visit_downstream(root)
    return ordered


def _dependent_summary(dependent: object) -> dict[str, object]:
    return {
        "name": str(getattr(dependent, "Name", "")),
        "type": str(getattr(dependent, "TypeId", "?")),
        "state": str(getattr(dependent, "State", "")),
    }


def _dependents(root: object) -> list[object]:
    return list(_object_dependents(root))


def _is_container(obj: object) -> bool:
    derived = getattr(obj, "isDerivedFrom", None)
    if callable(derived):
        try:
            return bool(
                derived("PartDesign::Body")
                or derived("App::DocumentObjectGroup")
                or derived("App::Part")
            )
        except Exception:
            pass
    type_id = str(getattr(obj, "TypeId", ""))
    return type_id in {"PartDesign::Body", "App::DocumentObjectGroup", "App::Part"}


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
        return DeleteObjectReceipt(
            name=root_name,
            deleted=(),
            refused=True,
            dependents=tuple(_dependent_summary(item) for item in dependents),
        )
    deleted: list[str] = []
    if request.recursive and _is_container(obj):
        # A Body/Part/Group removes its owned members. Deleting those members
        # one-by-one can touch restricted properties (MapReversed) across the
        # collaboration boundary. Capture names first, then remove the root.
        deleted.extend(dep_names)
        if get_object(doc, root_name) is not None:
            remove_object(doc, root_name)
            deleted.append(root_name)
        return DeleteObjectReceipt(name=root_name, deleted=tuple(deleted))
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
            validate=not self.request.force,
            recompute=not self.request.force,
        )
        if result is not True:
            return result
        if self.created is not None and self.created.refused:
            return make_delete_object_success(
                ObjectName(self.created.name),
                [],
                refused=True,
                dependents=list(self.created.dependents),
            )
        if self.inspected is None:
            return make_delete_object_uncertain(
                "DELETE_OBJECT_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected delete result",
                committed=True,
            )
        return make_delete_object_success(
            self.inspected.name,
            self.inspected.deleted,
            refused=False,
            recompute=(
                {
                    "policy": "deferred_recovery",
                    "required": True,
                    "message": (
                        "Run recompute_document after force deletion to settle the document."
                    ),
                }
                if self.request.force
                else None
            ),
        )


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
