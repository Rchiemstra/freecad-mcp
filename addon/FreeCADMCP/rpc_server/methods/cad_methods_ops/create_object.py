"""Typed ``create_object`` mutation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

try:
    from ...._shared.protocol.create_object_contract import (
        CreateObjectCollaborators,
        CreateObjectFailure,
        CreateObjectPayload,
        CreateObjectRequest,
        CreateObjectResult,
        DocumentName,
        ObjectName,
        ObjectType,
        make_create_object_failure,
        make_create_object_success,
        make_create_object_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.create_object_contract import (
        CreateObjectCollaborators,
        CreateObjectFailure,
        CreateObjectPayload,
        CreateObjectRequest,
        CreateObjectResult,
        DocumentName,
        ObjectName,
        ObjectType,
        make_create_object_failure,
        make_create_object_success,
        make_create_object_uncertain,
    )
from .create_object_mutation import CreateObjectError, run_create_object_native_mutation
from .property_postcondition import kept_property, property_kept_value
from .typed_rpc_document import add_object, assign_properties, get_object


@dataclass(frozen=True, slots=True)
class CreateObjectReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    obj: object
    object_type: str
    properties: tuple[tuple[str, object], ...]


@dataclass(frozen=True, slots=True)
class CreateObjectInspection:
    """Read-only data captured after the native-owned recompute."""

    name: ObjectName
    object_type: str
    label: str


def _failure(error: CreateObjectError, *, retry_safe: bool = True) -> CreateObjectFailure:
    return make_create_object_failure(
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


def apply_create_object(
    doc: object,
    request: CreateObjectRequest,
    set_object_property: Callable[[object, object, dict[str, object]], object] | None,
) -> CreateObjectReceipt:
    """Create an object without recomputing or managing a transaction."""

    if get_object(doc, str(request.object_name)) is not None:
        raise CreateObjectError(
            "OBJECT_ALREADY_EXISTS",
            f"Object already exists: {request.object_name!r}",
        )
    created = add_object(doc, str(request.object_type), str(request.object_name))
    properties = _resolve_link_properties(doc, dict(request.properties))
    if properties:
        if set_object_property is not None:
            set_object_property(doc, created, properties)
        else:
            assign_properties(created, properties)
    if request.analysis_name:
        analysis = get_object(doc, request.analysis_name)
        if analysis is None:
            raise CreateObjectError(
                "ANALYSIS_NOT_FOUND",
                f"Analysis not found: {request.analysis_name!r}",
            )
        adder = getattr(analysis, "addObject", None)
        if callable(adder):
            adder(created)
    assigned = getattr(created, "Name", str(request.object_name))
    if not isinstance(assigned, str) or not assigned.strip():
        raise CreateObjectError("CREATE_OBJECT_FAILED", "Created object has no name")
    return CreateObjectReceipt(
        name=assigned,
        obj=created,
        object_type=str(request.object_type),
        properties=tuple(
            (key, value)
            for key, value in properties.items()
            if key not in {"ShapeColor", "ViewObject"}
        ),
    )


def _is_type(obj: object, type_id: str) -> bool:
    derived = getattr(obj, "isDerivedFrom", None)
    if callable(derived):
        try:
            return bool(derived(type_id))
        except (AttributeError, TypeError):
            pass
    return getattr(obj, "TypeId", None) == type_id


def _resolve_link_properties(doc: object, properties: dict[str, object]) -> dict[str, object]:
    resolved: dict[str, object] = {}
    for key, value in properties.items():
        if (
            isinstance(value, str)
            and value.strip()
            and (
                key in {"LinkedObject", "Base", "Tool", "Source", "Profile", "Support", "Tip"}
                or key.endswith("Object")
                or key.endswith("Link")
            )
        ):
            target = get_object(doc, value)
            if target is not None:
                resolved[key] = target
                continue
        resolved[key] = value
    return resolved


def read_create_object_result(
    doc: object, receipt: CreateObjectReceipt
) -> CreateObjectInspection:
    """Build the public result after the shared mutation recompute."""

    created = get_object(doc, receipt.name)
    if created is None:
        raise CreateObjectError(
            "CREATED_OBJECT_MISSING",
            f"Created object is missing: {receipt.name!r}",
        )
    if created is not receipt.obj:
        raise CreateObjectError(
            "CREATED_OBJECT_REPLACED",
            f"Created object was replaced before commit: {receipt.name!r}",
        )
    if not _is_type(created, receipt.object_type):
        raise CreateObjectError(
            "CREATED_OBJECT_WRONG_TYPE",
            (
                f"Created object is not {receipt.object_type!r}: "
                f"{getattr(created, 'TypeId', None)!r}"
            ),
        )
    for key, expected in receipt.properties:
        if not hasattr(created, key):
            raise CreateObjectError(
                "PROPERTY_NOT_UPDATED",
                f"Created object is missing property {key!r}",
            )
        if not property_kept_value(doc, expected, kept_property(created, key)):
            raise CreateObjectError(
                "PROPERTY_NOT_UPDATED",
                f"Created object property {key!r} did not keep the assigned value",
            )
    label = getattr(created, "Label", receipt.name)
    type_id = getattr(created, "TypeId", receipt.object_type)
    return CreateObjectInspection(
        name=ObjectName(receipt.name),
        object_type=str(type_id),
        label=str(label),
    )


def build_create_object_request(
    doc_name: object, obj_data: object
) -> CreateObjectRequest | CreateObjectFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(CreateObjectError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    payload = _mapping(obj_data)
    if payload is None:
        return _failure(CreateObjectError("INVALID_ARGUMENT", "obj_data must be an object"))
    raw_name = payload.get("Name", "New_Object")
    raw_type = payload.get("Type")
    if not isinstance(raw_name, str) or not raw_name.strip():
        return _failure(CreateObjectError("INVALID_ARGUMENT", "Name must be a nonempty string"))
    if not isinstance(raw_type, str) or not raw_type.strip():
        return _failure(CreateObjectError("INVALID_ARGUMENT", "Type must be a nonempty string"))
    properties_raw = payload.get("Properties", {})
    properties = _mapping(properties_raw)
    if properties is None:
        return _failure(CreateObjectError("INVALID_ARGUMENT", "Properties must be an object"))
    analysis = payload.get("Analysis")
    if analysis is not None and not isinstance(analysis, str):
        return _failure(CreateObjectError("INVALID_ARGUMENT", "Analysis must be a string or null"))
    analysis_name = analysis.strip() if isinstance(analysis, str) and analysis.strip() else None
    return CreateObjectRequest(
        doc_name=DocumentName(doc_name),
        object_name=ObjectName(raw_name),
        object_type=ObjectType(raw_type),
        properties=tuple(properties.items()),
        analysis_name=analysis_name,
    )


@dataclass(slots=True)
class _CreateObjectExecution:
    collaborators: CreateObjectCollaborators
    request: CreateObjectRequest
    set_object_property: Callable[[object, object, dict[str, object]], object] | None
    created: CreateObjectReceipt | None = None
    inspected: CreateObjectInspection | None = None

    def apply(self, doc: object) -> None:
        self.created = apply_create_object(doc, self.request, self.set_object_property)

    def inspect(self, doc: object) -> None:
        if self.created is None:
            raise CreateObjectError(
                "INVALID_CREATE_OBJECT_RESULT",
                "Object creation did not return an identity receipt",
            )
        self.inspected = read_create_object_result(doc, self.created)

    def run(self) -> CreateObjectResult:
        result = run_create_object_native_mutation(
            self.collaborators,
            str(self.request.doc_name),
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_create_object_uncertain(
                "CREATE_OBJECT_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected object result",
                committed=True,
            )
        return make_create_object_success(
            self.inspected.name, self.inspected.object_type, self.inspected.label
        )


def run_create_object(
    collaborators: CreateObjectCollaborators,
    doc_name: object,
    obj_data: object,
    set_object_property: Callable[[object, object, dict[str, object]], object] | None = None,
) -> CreateObjectResult:
    """Run object creation through apply, recompute, inspection, and commit."""

    request = build_create_object_request(doc_name, obj_data)
    if isinstance(request, dict):
        return request
    return _CreateObjectExecution(collaborators, request, set_object_property).run()


class _CreateObjectRpcFacade(Protocol):
    _cad_collaborators: CreateObjectCollaborators

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


def rpc_create_object(
    self: _CreateObjectRpcFacade,
    doc_name: str,
    obj_data: object,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    setter = _property_setter(collaborators)
    res = self._dispatch_gui(
        lambda: run_create_object(collaborators, doc_name, obj_data, setter)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("create_object", rpc_create_object)


__all__ = [
    "CreateObjectCollaborators",
    "CreateObjectError",
    "CreateObjectInspection",
    "CreateObjectPayload",
    "CreateObjectReceipt",
    "apply_create_object",
    "build_create_object_request",
    "read_create_object_result",
    "rpc_create_object",
    "run_create_object",
    "TYPED_RPC_HANDLER",
]
