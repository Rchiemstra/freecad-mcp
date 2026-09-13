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
from .typed_rpc_support import (
    add_named_object,
    add_to_container,
    as_bool,
    as_float,
    as_int,
    assign_attr,
    call_named,
    invoke,
    nonempty_string,
    object_label,
    object_name,
    object_type_id,
    optional_string,
    parse_ref,
    remove_from_container,
    require_object,
    resolve_if_exists,
    snapshot_ring
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


def apply_create_placement_binder(doc: CreatePlacementBinderDocument, request: CreatePlacementBinderRequest) -> CreatePlacementBinderReceipt:
    """Create a SubShapeBinder without recomputing."""

    owner = require_object(doc, request.owner_body, missing_code="OBJECT_NOT_FOUND", error=CreatePlacementBinderError) if request.owner_body else None
    source_obj = require_object(doc, request.source, missing_code="OBJECT_NOT_FOUND", error=CreatePlacementBinderError)
    created = add_named_object(doc, "PartDesign::SubShapeBinder", request.name)
    if owner is not None:
        add_to_container(owner, created)
    assign_attr(created, "Support", [(source_obj, "")])
    return CreatePlacementBinderReceipt(name=object_name(created) or request.name, item=created, skipped=False)


def read_create_placement_binder_result(doc: CreatePlacementBinderReadDocument, receipt: CreatePlacementBinderReceipt) -> CreatePlacementBinderInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        located = receipt.item
    if located is None:
        raise CreatePlacementBinderError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if (
        receipt.item is not None
        and located is not receipt.item
        and object_name(located) != receipt.name
    ):
        raise CreatePlacementBinderError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")

    extra = receipt.extra

    return CreatePlacementBinderInspection(
        name=CreatePlacementBinderName(receipt.name),
        label=object_label(located),
        extra=extra,
    )


def build_create_placement_binder_request(doc_name: object, owner_body: object, name: object, source: object, relative: object, bind_mode: object) -> CreatePlacementBinderRequest | CreatePlacementBinderFailure:
    doc_name_value = nonempty_string(doc_name, 'doc_name')
    if doc_name_value is None:
        return _failure(CreatePlacementBinderError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    owner_body_value = nonempty_string(owner_body, 'owner_body')
    if owner_body_value is None:
        return _failure(CreatePlacementBinderError("INVALID_ARGUMENT", "owner_body must be a nonempty string"))
    name_value = nonempty_string(name, 'name')
    if name_value is None:
        return _failure(CreatePlacementBinderError("INVALID_ARGUMENT", "name must be a nonempty string"))
    source_value = nonempty_string(source, 'source')
    if source_value is None:
        return _failure(CreatePlacementBinderError("INVALID_ARGUMENT", "source must be a nonempty string"))
    relative_value = as_bool(relative, True)
    if relative_value is None:
        return _failure(CreatePlacementBinderError("INVALID_ARGUMENT", "relative must be a boolean"))
    bind_mode_value = nonempty_string(bind_mode, 'bind_mode')
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
