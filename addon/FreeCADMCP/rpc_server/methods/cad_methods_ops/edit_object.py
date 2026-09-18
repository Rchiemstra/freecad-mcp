"""Typed ``edit_object`` mutation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

try:
    from ...._shared.protocol.edit_object_contract import (
        DocumentName,
        EditObjectCollaborators,
        EditObjectFailure,
        EditObjectRequest,
        EditObjectResult,
        ObjectName,
        make_edit_object_failure,
        make_edit_object_success,
        make_edit_object_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.edit_object_contract import (
        DocumentName,
        EditObjectCollaborators,
        EditObjectFailure,
        EditObjectRequest,
        EditObjectResult,
        ObjectName,
        make_edit_object_failure,
        make_edit_object_success,
        make_edit_object_uncertain,
    )
from .edit_object_mutation import EditObjectError, run_edit_object_native_mutation
from .typed_rpc_document import assign_properties, get_object


@dataclass(frozen=True, slots=True)
class EditObjectReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    obj: object
    properties: tuple[tuple[str, object], ...]


@dataclass(frozen=True, slots=True)
class EditObjectInspection:
    """Read-only data captured after the native-owned recompute."""

    name: ObjectName
    label: str


def _failure(error: EditObjectError, *, retry_safe: bool = True) -> EditObjectFailure:
    return make_edit_object_failure(
        error.code, str(error), retry_safe=retry_safe, diagnostics=error.diagnostics
    )


def _mapping(raw: object) -> dict[str, object] | None:
    if not isinstance(raw, Mapping):
        return None
    result: dict[str, object] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            return None
        result[key] = value
    return result


def apply_edit_object(
    doc: object,
    request: EditObjectRequest,
    set_object_property: Callable[[object, object, dict[str, object]], object] | None,
) -> EditObjectReceipt:
    """Edit an object without recomputing or managing a transaction."""

    obj = get_object(doc, str(request.object_name))
    if obj is None:
        raise EditObjectError(
            "OBJECT_NOT_FOUND",
            f"Object not found: {request.object_name!r}",
        )
    properties = dict(request.properties)
    if properties:
        if set_object_property is not None:
            set_object_property(doc, obj, properties)
        else:
            assign_properties(obj, properties)
    assigned = [
        (key, value)
        for key, value in properties.items()
        if key not in {"ShapeColor", "ViewObject"}
    ]
    return EditObjectReceipt(
        name=str(getattr(obj, "Name", request.object_name)),
        obj=obj,
        properties=tuple(assigned),
    )


def _scalar_property(value: object) -> object:
    return getattr(value, "Value", value)


def _property_matches(expected: object, actual: object) -> bool:
    left = _scalar_property(expected)
    right = _scalar_property(actual)
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= 1e-6
    return left == right


def read_edit_object_result(doc: object, receipt: EditObjectReceipt) -> EditObjectInspection:
    """Build the public result after the shared mutation recompute."""

    edited = get_object(doc, receipt.name)
    if edited is None:
        raise EditObjectError(
            "EDITED_OBJECT_MISSING",
            f"Edited object is missing: {receipt.name!r}",
        )
    if edited is not receipt.obj:
        raise EditObjectError(
            "EDITED_OBJECT_REPLACED",
            f"Edited object was replaced before commit: {receipt.name!r}",
        )
    for key, expected in receipt.properties:
        if not hasattr(edited, key):
            raise EditObjectError(
                "PROPERTY_NOT_UPDATED",
                f"Edited object is missing property {key!r}",
            )
        if not _property_matches(expected, getattr(edited, key)):
            raise EditObjectError(
                "PROPERTY_NOT_UPDATED",
                f"Edited object property {key!r} did not keep the assigned value",
            )
    return EditObjectInspection(
        name=ObjectName(receipt.name),
        label=str(getattr(edited, "Label", receipt.name)),
    )


def build_edit_object_request(
    doc_name: object, obj_name: object, properties: object
) -> EditObjectRequest | EditObjectFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(EditObjectError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(obj_name, str) or not obj_name.strip():
        return _failure(EditObjectError("INVALID_ARGUMENT", "obj_name must be a nonempty string"))
    payload = _mapping(properties)
    if payload is None:
        return _failure(EditObjectError("INVALID_ARGUMENT", "properties must be an object"))
    inner = payload.get("Properties", payload)
    mapped = _mapping(inner) if inner is not payload else payload
    if mapped is None:
        return _failure(EditObjectError("INVALID_ARGUMENT", "Properties must be an object"))
    if inner is not payload:
        mapped = _mapping(inner)
        if mapped is None:
            return _failure(EditObjectError("INVALID_ARGUMENT", "Properties must be an object"))
    return EditObjectRequest(
        doc_name=DocumentName(doc_name),
        object_name=ObjectName(obj_name),
        properties=tuple(mapped.items()),
    )


@dataclass(slots=True)
class _EditObjectExecution:
    collaborators: EditObjectCollaborators
    request: EditObjectRequest
    set_object_property: Callable[[object, object, dict[str, object]], object] | None
    created: EditObjectReceipt | None = None
    inspected: EditObjectInspection | None = None

    def apply(self, doc: object) -> None:
        self.created = apply_edit_object(doc, self.request, self.set_object_property)

    def inspect(self, doc: object) -> None:
        if self.created is None:
            raise EditObjectError(
                "INVALID_EDIT_OBJECT_RESULT",
                "Object edit did not return an identity receipt",
            )
        self.inspected = read_edit_object_result(doc, self.created)

    def run(self) -> EditObjectResult:
        result = run_edit_object_native_mutation(
            self.collaborators,
            str(self.request.doc_name),
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_edit_object_uncertain(
                "EDIT_OBJECT_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected edit result",
                committed=True,
            )
        return make_edit_object_success(self.inspected.name, self.inspected.label)


def run_edit_object(
    collaborators: EditObjectCollaborators,
    doc_name: object,
    obj_name: object,
    properties: object,
    set_object_property: Callable[[object, object, dict[str, object]], object] | None = None,
) -> EditObjectResult:
    """Run object editing through apply, recompute, inspection, and commit."""

    request = build_edit_object_request(doc_name, obj_name, properties)
    if isinstance(request, dict):
        return request
    return _EditObjectExecution(collaborators, request, set_object_property).run()


class _EditObjectRpcFacade(Protocol):
    _cad_collaborators: EditObjectCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def _property_setter(
    collaborators: object,
) -> Callable[[object, object, dict[str, object]], object] | None:
    setter = getattr(collaborators, "set_object_property", None)
    if not callable(setter):
        return None

    def _set(document: object, obj: object, properties: dict[str, object]) -> object:
        return setter(document, obj, properties)

    return _set


def rpc_edit_object(
    self: _EditObjectRpcFacade,
    doc_name: str,
    obj_name: str,
    properties: object,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    setter = _property_setter(collaborators)
    res = self._dispatch_gui(
        lambda: run_edit_object(collaborators, doc_name, obj_name, properties, setter)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("edit_object", rpc_edit_object)


__all__ = [
    "EditObjectCollaborators",
    "EditObjectError",
    "EditObjectInspection",
    "EditObjectReceipt",
    "apply_edit_object",
    "build_edit_object_request",
    "read_edit_object_result",
    "rpc_edit_object",
    "run_edit_object",
    "TYPED_RPC_HANDLER",
]
