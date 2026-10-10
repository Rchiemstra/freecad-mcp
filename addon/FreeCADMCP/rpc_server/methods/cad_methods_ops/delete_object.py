"""Typed ``delete_object`` mutation."""

from __future__ import annotations

from .native_commit_wait import NativeOutcome, continue_after_native_commit

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

try:
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
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.delete_object_contract import (
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
    orphans: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DeleteObjectInspection:
    """Read-only data captured after the native-owned recompute."""

    name: ObjectName
    deleted: list[str]
    orphans_left: list[object]


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
        # Links and link-array elements reference the body from outside Group.
        # They would be left dangling, so the refusal has to name them too.
        for dependent in _links(root, "InList"):
            if _owns(dependent, root):
                seen.add(id(dependent))
                continue
            visit_downstream(dependent)
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


def object_dependents(root: object) -> list[object]:
    """Objects that would be orphaned without *root*, leaves first (deletion order)."""

    return list(_object_dependents(root))


_dependents = object_dependents


def _remove(doc: object, name: str) -> None:
    """Remove *name*, letting an owning PartDesign Body move its Tip first.

    Document.removeObject knows nothing about bodies. FreeCAD's own delete
    calls Body.removeObject beforehand (PartDesignGui::ViewProvider::onDelete);
    without it, deleting the Tip feature left the Body with no shape.
    """
    item = get_object(doc, name)
    owner = _owning_container(item) if item is not None else None
    if owner is not None and _is_derived(owner, "PartDesign::Body"):
        detach = getattr(owner, "removeObject", None)
        if callable(detach):
            detach(item)
    remove_object(doc, name)


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
            "OBJECT_HAS_DEPENDENTS",
            f"Refused to delete {root_name!r}: {len(dep_names)} dependent(s) would be "
            f"orphaned ({', '.join(dep_names)}). Pass recursive=true to delete them "
            "too, or force=true to delete only this object.",
            diagnostics={
                "refused": True,
                "dependents": [_dependent_summary(item) for item in dependents],
            },
        )
    deleted: list[str] = []
    delete_order = [*dep_names, root_name] if request.recursive else [root_name]
    remaining = [name for name in delete_order if name]
    # KEEP BOTH: historical GUI order deletes deepest dependents then the
    # root. The typed container shortcut only removed the Body, which left
    # sketch/pad behind once MapReversed extras allowed the root to drop.
    # Try dependents first, then the root, then any leftovers after the
    # container unsetup.
    for name in list(remaining):
        if get_object(doc, name) is None:
            if name not in deleted:
                deleted.append(name)
            continue
        try:
            _remove(doc, name)
        except Exception:
            continue
        if get_object(doc, name) is None and name not in deleted:
            deleted.append(name)
    if get_object(doc, root_name) is not None:
        _remove(doc, root_name)
        if get_object(doc, root_name) is None and root_name not in deleted:
            deleted.append(root_name)
    for name in remaining:
        if get_object(doc, name) is None:
            if name not in deleted:
                deleted.append(name)
            continue
        try:
            _remove(doc, name)
        except Exception:
            continue
        if get_object(doc, name) is None and name not in deleted:
            deleted.append(name)
    orphans = tuple(name for name in dep_names if name not in deleted)
    return DeleteObjectReceipt(name=root_name, deleted=tuple(deleted), orphans=orphans)


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
    orphans_left: list[object] = []
    for name in receipt.orphans:
        orphan = get_object(doc, name)
        if orphan is not None:
            orphans_left.append(_dependent_summary(orphan))
    return DeleteObjectInspection(
        name=ObjectName(receipt.name),
        deleted=list(receipt.deleted),
        orphans_left=orphans_left,
    )


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

    def run(self) -> NativeOutcome[DeleteObjectResult]:
        result = run_delete_object_native_mutation(
            self.collaborators,
            str(self.request.doc_name),
            self.apply,
            self.inspect,
            validate=not self.request.force,
            recompute=not self.request.force,
        )
        def _finish_native_commit() -> DeleteObjectResult:
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
                orphans_left=self.inspected.orphans_left if self.request.force else None,
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

        return continue_after_native_commit(result, _finish_native_commit)

def run_delete_object(
    collaborators: DeleteObjectCollaborators,
    doc_name: object,
    obj_name: object,
    recursive: object = False,
    force: object = False,
) -> NativeOutcome[DeleteObjectResult]:
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
    "object_dependents",
    "read_delete_object_result",
    "rpc_delete_object",
    "run_delete_object",
    "TYPED_RPC_HANDLER",
]
