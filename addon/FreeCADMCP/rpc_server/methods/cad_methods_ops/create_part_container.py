"""Typed ``create_part_container`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.create_part_container_contract import (
    CreatePartContainerCollaborators,
    CreatePartContainerDocument,
    CreatePartContainerFailure,
    CreatePartContainerName,
    CreatePartContainerReadDocument,
    CreatePartContainerRequest,
    CreatePartContainerResult,
    DocumentName,
    make_create_part_container_failure,
    make_create_part_container_success,
    make_create_part_container_uncertain,
)
from .create_part_container_mutation import CreatePartContainerError, run_create_part_container_native_mutation
from .typed_rpc_support import (
    add_named_object,
    add_to_container,
    nonempty_string,
    object_label,
    object_name,
    object_type_id,
    optional_string,
    require_object,
    resolve_if_exists,
)


@dataclass(frozen=True, slots=True)
class CreatePartContainerReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    skipped: bool = False
    extra: object = None


@dataclass(frozen=True, slots=True)
class CreatePartContainerInspection:
    """Read-only data captured after the native-owned recompute."""

    name: CreatePartContainerName
    label: str
    extra: object = None


def _failure(error: CreatePartContainerError, *, retry_safe: bool = True) -> CreatePartContainerFailure:
    return make_create_part_container_failure(error.code, str(error), retry_safe=retry_safe)


def _object_in_owner(located: object, owner: object) -> bool:
    group = list(getattr(owner, "Group", None) or [])
    if located in group:
        return True
    in_list = list(getattr(located, "InList", None) or [])
    return owner in in_list


def apply_create_part_container(doc: CreatePartContainerDocument, request: CreatePartContainerRequest) -> CreatePartContainerReceipt:
    """Create an App::Part without recomputing or managing a transaction."""

    skipped = resolve_if_exists(doc, request.part_name, request.if_exists, error=CreatePartContainerError)
    if skipped is not None:
        return CreatePartContainerReceipt(name=object_name(skipped) or request.part_name, item=skipped, skipped=True)
    created = add_named_object(doc, "App::Part", request.part_name)
    parent_name = None
    if request.parent_container:
        parent = require_object(
            doc,
            request.parent_container,
            missing_code="OBJECT_NOT_FOUND",
            error=CreatePartContainerError,
        )
        add_to_container(parent, created)
        parent_name = object_name(parent)
    return CreatePartContainerReceipt(
        name=object_name(created) or request.part_name,
        item=created,
        skipped=False,
        extra={"parent_container": parent_name},
    )


def read_create_part_container_result(doc: CreatePartContainerReadDocument, receipt: CreatePartContainerReceipt) -> CreatePartContainerInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        raise CreatePartContainerError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if receipt.item is not None and located is not receipt.item:
        raise CreatePartContainerError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")

    type_id = object_type_id(located)
    if "App::Part" not in type_id:
        raise CreatePartContainerError("CREATED_OBJECT_WRONG_TYPE", f"Created object is not App::Part: {receipt.name!r}")

    parent_name = None
    if isinstance(receipt.extra, dict):
        parent_name = receipt.extra.get("parent_container")
    if parent_name:
        parent = doc.getObject(str(parent_name))
        if parent is not None and not _object_in_owner(located, parent):
            raise CreatePartContainerError(
                "POSTCONDITION_FAILED",
                f"Part container is not grouped under parent: {parent_name!r}",
            )

    return CreatePartContainerInspection(
        name=CreatePartContainerName(receipt.name),
        label=object_label(located),
        extra=receipt.extra,
    )


def build_create_part_container_request(doc_name: object, part_name: object, parent_container: object, if_exists: object) -> CreatePartContainerRequest | CreatePartContainerFailure:
    doc_name_value = nonempty_string(doc_name, "doc_name")
    if doc_name_value is None:
        return _failure(CreatePartContainerError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    part_name_value = nonempty_string(part_name, "part_name")
    if part_name_value is None:
        return _failure(CreatePartContainerError("INVALID_ARGUMENT", "part_name must be a nonempty string"))
    if parent_container is None:
        parent_container_value: str | None = None
    else:
        parent_container_value = optional_string(parent_container)
        if parent_container_value is None:
            return _failure(CreatePartContainerError("INVALID_ARGUMENT", "parent_container must be a nonempty string or None"))
    if_exists_value = nonempty_string(if_exists, "if_exists")
    if if_exists_value is None:
        return _failure(CreatePartContainerError("INVALID_ARGUMENT", "if_exists must be a nonempty string"))
    if if_exists_value not in {"error", "skip", "replace"}:
        return _failure(CreatePartContainerError("INVALID_ARGUMENT", "if_exists must be one of: error, skip, replace"))
    return CreatePartContainerRequest(
        doc_name=DocumentName(doc_name_value),
        part_name=part_name_value,
        parent_container=parent_container_value,
        if_exists=if_exists_value,
    )


@dataclass(slots=True)
class _CreatePartContainerExecution:
    collaborators: CreatePartContainerCollaborators
    request: CreatePartContainerRequest
    created: CreatePartContainerReceipt | None = None
    inspected: CreatePartContainerInspection | None = None

    def apply(self, doc: CreatePartContainerDocument) -> None:
        self.created = apply_create_part_container(doc, self.request)

    def inspect(self, doc: CreatePartContainerReadDocument) -> None:
        if self.created is None:
            raise CreatePartContainerError(
                "INVALID_CREATE_PART_CONTAINER_RESULT",
                "create_part_container did not return an identity receipt",
            )
        self.inspected = read_create_part_container_result(doc, self.created)

    def run(self) -> CreatePartContainerResult:
        result = run_create_part_container_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_create_part_container_uncertain(
                "CREATE_PART_CONTAINER_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        return make_create_part_container_success(part_name=self.inspected.name, label=self.inspected.label)


def run_create_part_container(
    collaborators: CreatePartContainerCollaborators,
    doc_name: object, part_name: object, parent_container: object, if_exists: object,
) -> CreatePartContainerResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_create_part_container_request(doc_name, part_name, parent_container, if_exists)
    if isinstance(request, dict):
        return request
    return _CreatePartContainerExecution(collaborators, request).run()


class _CreatePartContainerRpcFacade(Protocol):
    _cad_collaborators: CreatePartContainerCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_create_part_container(
    self: _CreatePartContainerRpcFacade, doc_name: str, part_name: str, parent_container: str | None = None, if_exists: str = "error",
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_create_part_container(collaborators, doc_name, part_name, parent_container, if_exists)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("create_part_container", rpc_create_part_container)


__all__ = [
    "CreatePartContainerCollaborators",
    "CreatePartContainerError",
    "CreatePartContainerInspection",
    "CreatePartContainerReceipt",
    "apply_create_part_container",
    "build_create_part_container_request",
    "read_create_part_container_result",
    "rpc_create_part_container",
    "run_create_part_container",
    "TYPED_RPC_HANDLER",
]
