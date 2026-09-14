"""Typed ``create_placement_datum`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.create_placement_datum_contract import (
    CreatePlacementDatumCollaborators,
    CreatePlacementDatumDocument,
    CreatePlacementDatumFailure,
    CreatePlacementDatumName,
    CreatePlacementDatumReadDocument,
    CreatePlacementDatumRequest,
    CreatePlacementDatumResult,
    DocumentName,
    make_create_placement_datum_failure,
    make_create_placement_datum_success,
    make_create_placement_datum_uncertain,
)
from .create_placement_datum_mutation import CreatePlacementDatumError, run_create_placement_datum_native_mutation
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
class CreatePlacementDatumReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    skipped: bool = False
    extra: object = None


@dataclass(frozen=True, slots=True)
class CreatePlacementDatumInspection:
    """Read-only data captured after the native-owned recompute."""

    name: CreatePlacementDatumName
    label: str
    extra: object = None


def _failure(error: CreatePlacementDatumError, *, retry_safe: bool = True) -> CreatePlacementDatumFailure:
    return make_create_placement_datum_failure(error.code, str(error), retry_safe=retry_safe)


def apply_create_placement_datum(doc: CreatePlacementDatumDocument, request: CreatePlacementDatumRequest) -> CreatePlacementDatumReceipt:
    """Create a placement-aware datum without recomputing."""

    body = require_object(doc, request.owner_body, missing_code="OBJECT_NOT_FOUND", error=CreatePlacementDatumError)
    plane = call_named(body, "newObject", "PartDesign::Plane", request.name)
    if plane is None:
        plane = add_named_object(doc, "PartDesign::Plane", request.name)
        add_to_container(body, plane)
    obj, sub = parse_ref(doc, request.source, CreatePlacementDatumError)
    assign_attr(plane, "AttachmentSupport", [(obj, sub)])
    return CreatePlacementDatumReceipt(name=object_name(plane) or request.name, item=plane, skipped=False)


def read_create_placement_datum_result(doc: CreatePlacementDatumReadDocument, receipt: CreatePlacementDatumReceipt) -> CreatePlacementDatumInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        located = receipt.item
    if located is None:
        raise CreatePlacementDatumError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if (
        receipt.item is not None
        and located is not receipt.item
        and object_name(located) != receipt.name
    ):
        raise CreatePlacementDatumError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")

    extra = receipt.extra

    return CreatePlacementDatumInspection(
        name=CreatePlacementDatumName(receipt.name),
        label=object_label(located),
        extra=extra,
    )


def build_create_placement_datum_request(doc_name: object, owner_body: object, name: object, source: object, relative: object, offset: object) -> CreatePlacementDatumRequest | CreatePlacementDatumFailure:
    doc_name_value = nonempty_string(doc_name, 'doc_name')
    if doc_name_value is None:
        return _failure(CreatePlacementDatumError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    owner_body_value = nonempty_string(owner_body, 'owner_body')
    if owner_body_value is None:
        return _failure(CreatePlacementDatumError("INVALID_ARGUMENT", "owner_body must be a nonempty string"))
    name_value = nonempty_string(name, 'name')
    if name_value is None:
        return _failure(CreatePlacementDatumError("INVALID_ARGUMENT", "name must be a nonempty string"))
    source_value = nonempty_string(source, 'source')
    if source_value is None:
        return _failure(CreatePlacementDatumError("INVALID_ARGUMENT", "source must be a nonempty string"))
    relative_value = as_bool(relative, True)
    if relative_value is None:
        return _failure(CreatePlacementDatumError("INVALID_ARGUMENT", "relative must be a boolean"))
    return CreatePlacementDatumRequest(
        doc_name=DocumentName(doc_name_value),
        owner_body=owner_body_value,
        name=name_value,
        source=source_value,
        relative=relative_value,
        offset=offset,
    )


@dataclass(slots=True)
class _CreatePlacementDatumExecution:
    collaborators: CreatePlacementDatumCollaborators
    request: CreatePlacementDatumRequest
    created: CreatePlacementDatumReceipt | None = None
    inspected: CreatePlacementDatumInspection | None = None

    def apply(self, doc: CreatePlacementDatumDocument) -> None:
        self.created = apply_create_placement_datum(doc, self.request)

    def inspect(self, doc: CreatePlacementDatumReadDocument) -> None:
        if self.created is None:
            raise CreatePlacementDatumError(
                "INVALID_CREATE_PLACEMENT_DATUM_RESULT",
                "create_placement_datum did not return an identity receipt",
            )
        self.inspected = read_create_placement_datum_result(doc, self.created)

    def run(self) -> CreatePlacementDatumResult:
        result = run_create_placement_datum_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_create_placement_datum_uncertain(
                "CREATE_PLACEMENT_DATUM_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        return make_create_placement_datum_success(datum_name=self.inspected.name)


def run_create_placement_datum(
    collaborators: CreatePlacementDatumCollaborators,
    doc_name: object, owner_body: object, name: object, source: object, relative: object, offset: object,
) -> CreatePlacementDatumResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_create_placement_datum_request(doc_name, owner_body, name, source, relative, offset)
    if isinstance(request, dict):
        return request
    return _CreatePlacementDatumExecution(collaborators, request).run()


class _CreatePlacementDatumRpcFacade(Protocol):
    _cad_collaborators: CreatePlacementDatumCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_create_placement_datum(
    self: _CreatePlacementDatumRpcFacade, doc_name: str, owner_body: str, name: str, source: str, relative: bool = True, offset: object = None,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_create_placement_datum(collaborators, doc_name, owner_body, name, source, relative, offset)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("create_placement_datum", rpc_create_placement_datum)


__all__ = [
    "CreatePlacementDatumCollaborators",
    "CreatePlacementDatumError",
    "CreatePlacementDatumInspection",
    "CreatePlacementDatumReceipt",
    "apply_create_placement_datum",
    "build_create_placement_datum_request",
    "read_create_placement_datum_result",
    "rpc_create_placement_datum",
    "run_create_placement_datum",
    "TYPED_RPC_HANDLER",
]
