"""Typed ``create_placement_binder`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.create_placement_binder_contract import (
    CreatePlacementBinderCollaborators,
    CreatePlacementBinderDocument,
    CreatePlacementBinderFailure,
    CreatePlacementBinderName,
    CreatePlacementBinderReadDocument,
    CreatePlacementBinderRequest,
    CreatePlacementBinderResult,
    DocumentName,
    make_create_placement_binder_failure,
    make_create_placement_binder_success,
    make_create_placement_binder_uncertain,
)
from .create_placement_binder_mutation import CreatePlacementBinderError, run_create_placement_binder_native_mutation
from .typed_runtime import is_derived_from
from .typed_rpc_support import (
    as_bool,
    assign_attr,
    nonempty_string,
    object_label,
    object_name,
    object_type_id,
    require_object,
)


@dataclass(frozen=True, slots=True)
class CreatePlacementBinderReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    skipped: bool = False
    extra: object = None


@dataclass(frozen=True, slots=True)
class CreatePlacementBinderInspection:
    """Read-only data captured after the native-owned recompute."""

    name: CreatePlacementBinderName
    label: str
    extra: object = None


def _failure(error: CreatePlacementBinderError, *, retry_safe: bool = True) -> CreatePlacementBinderFailure:
    return make_create_placement_binder_failure(error.code, str(error), retry_safe=retry_safe)


def _object_in_owner(located: object, owner: object) -> bool:
    group = list(getattr(owner, "Group", None) or [])
    if located in group:
        return True
    in_list = list(getattr(located, "InList", None) or [])
    return owner in in_list


def apply_create_placement_binder(doc: CreatePlacementBinderDocument, request: CreatePlacementBinderRequest) -> CreatePlacementBinderReceipt:
    """Create a SubShapeBinder without recomputing."""

    owner = require_object(doc, request.owner_body, missing_code="OBJECT_NOT_FOUND", error=CreatePlacementBinderError)
    source_obj = require_object(doc, request.source, missing_code="OBJECT_NOT_FOUND", error=CreatePlacementBinderError)
    factory = getattr(owner, "newObject", None)
    if not callable(factory):
        raise CreatePlacementBinderError("INVALID_BODY", "owner_body must provide newObject")
    created = factory("PartDesign::SubShapeBinder", request.name)
    if created is None:
        raise CreatePlacementBinderError(
            "CREATE_FAILED",
            f"Failed to create PartDesign::SubShapeBinder: {request.name!r}",
        )
    assign_attr(created, "Support", [(source_obj, "")])
    assign_attr(created, "Relative", request.relative)
    assign_attr(created, "BindMode", request.bind_mode)
    return CreatePlacementBinderReceipt(
        name=object_name(created) or request.name,
        item=created,
        skipped=False,
        extra={"owner_name": object_name(owner)},
    )


def read_create_placement_binder_result(doc: CreatePlacementBinderReadDocument, receipt: CreatePlacementBinderReceipt) -> CreatePlacementBinderInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        raise CreatePlacementBinderError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if receipt.item is not None and located is not receipt.item:
        raise CreatePlacementBinderError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")

    type_id = object_type_id(located)
    if "SubShapeBinder" not in type_id and not is_derived_from(located, "PartDesign::SubShapeBinder"):
        raise CreatePlacementBinderError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Created object is not PartDesign::SubShapeBinder: {receipt.name!r}",
        )

    owner_name = None
    if isinstance(receipt.extra, dict):
        owner_name = receipt.extra.get("owner_name")
    if owner_name:
        owner = doc.getObject(str(owner_name))
        if owner is not None and not _object_in_owner(located, owner):
            raise CreatePlacementBinderError(
                "POSTCONDITION_FAILED",
                f"Binder is not grouped under owner: {owner_name!r}",
            )

    return CreatePlacementBinderInspection(
        name=CreatePlacementBinderName(receipt.name),
        label=object_label(located),
        extra=receipt.extra,
    )


def build_create_placement_binder_request(doc_name: object, owner_body: object, name: object, source: object, relative: object, bind_mode: object) -> CreatePlacementBinderRequest | CreatePlacementBinderFailure:
    doc_name_value = nonempty_string(doc_name, "doc_name")
    if doc_name_value is None:
        return _failure(CreatePlacementBinderError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    owner_body_value = nonempty_string(owner_body, "owner_body")
    if owner_body_value is None:
        return _failure(CreatePlacementBinderError("INVALID_ARGUMENT", "owner_body must be a nonempty string"))
    name_value = nonempty_string(name, "name")
    if name_value is None:
        return _failure(CreatePlacementBinderError("INVALID_ARGUMENT", "name must be a nonempty string"))
    source_value = nonempty_string(source, "source")
    if source_value is None:
        return _failure(CreatePlacementBinderError("INVALID_ARGUMENT", "source must be a nonempty string"))
    relative_value = as_bool(relative, True)
    if relative_value is None:
        return _failure(CreatePlacementBinderError("INVALID_ARGUMENT", "relative must be a boolean"))
    bind_mode_value = nonempty_string(bind_mode, "bind_mode")
    if bind_mode_value is None:
        return _failure(CreatePlacementBinderError("INVALID_ARGUMENT", "bind_mode must be a nonempty string"))
    return CreatePlacementBinderRequest(
        doc_name=DocumentName(doc_name_value),
        owner_body=owner_body_value,
        name=name_value,
        source=source_value,
        relative=relative_value,
        bind_mode=bind_mode_value,
    )


@dataclass(slots=True)
class _CreatePlacementBinderExecution:
    collaborators: CreatePlacementBinderCollaborators
    request: CreatePlacementBinderRequest
    created: CreatePlacementBinderReceipt | None = None
    inspected: CreatePlacementBinderInspection | None = None

    def apply(self, doc: CreatePlacementBinderDocument) -> None:
        self.created = apply_create_placement_binder(doc, self.request)

    def inspect(self, doc: CreatePlacementBinderReadDocument) -> None:
        if self.created is None:
            raise CreatePlacementBinderError(
                "INVALID_CREATE_PLACEMENT_BINDER_RESULT",
                "create_placement_binder did not return an identity receipt",
            )
        self.inspected = read_create_placement_binder_result(doc, self.created)

    def run(self) -> CreatePlacementBinderResult:
        result = run_create_placement_binder_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_create_placement_binder_uncertain(
                "CREATE_PLACEMENT_BINDER_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        return make_create_placement_binder_success(binder_name=self.inspected.name)


def run_create_placement_binder(
    collaborators: CreatePlacementBinderCollaborators,
    doc_name: object, owner_body: object, name: object, source: object, relative: object, bind_mode: object,
) -> CreatePlacementBinderResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_create_placement_binder_request(doc_name, owner_body, name, source, relative, bind_mode)
    if isinstance(request, dict):
        return request
    return _CreatePlacementBinderExecution(collaborators, request).run()


class _CreatePlacementBinderRpcFacade(Protocol):
    _cad_collaborators: CreatePlacementBinderCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_create_placement_binder(
    self: _CreatePlacementBinderRpcFacade, doc_name: str, owner_body: str, name: str, source: str, relative: bool = True, bind_mode: str = "Synchronized",
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_create_placement_binder(collaborators, doc_name, owner_body, name, source, relative, bind_mode)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("create_placement_binder", rpc_create_placement_binder)


__all__ = [
    "CreatePlacementBinderCollaborators",
    "CreatePlacementBinderError",
    "CreatePlacementBinderInspection",
    "CreatePlacementBinderReceipt",
    "apply_create_placement_binder",
    "build_create_placement_binder_request",
    "read_create_placement_binder_result",
    "rpc_create_placement_binder",
    "run_create_placement_binder",
    "TYPED_RPC_HANDLER",
]
