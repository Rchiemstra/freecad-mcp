"""Typed ``body_create`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.body_create_contract import (
    BodyCreateCollaborators,
    BodyCreateFailure,
    BodyCreateRequest,
    BodyCreateResult,
    BodyDocument,
    BodyName,
    BodyObject,
    BodyReadDocument,
    DocumentName,
    make_body_create_failure,
    make_body_create_success,
    make_body_create_uncertain,
)
from .body_mutation import BodyCreateError, run_body_native_mutation


@dataclass(frozen=True, slots=True)
class BodyCreateReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    body: BodyObject


@dataclass(frozen=True, slots=True)
class BodyCreateInspection:
    """Read-only data captured after the native-owned recompute."""

    name: BodyName
    label: str


def _failure(error: BodyCreateError, *, retry_safe: bool = True) -> BodyCreateFailure:
    return make_body_create_failure(error.code, str(error), retry_safe=retry_safe)


def apply_body_create(doc: BodyDocument, body_name: BodyName) -> BodyCreateReceipt:
    """Create a Body without recomputing or managing a transaction."""

    if not isinstance(body_name, str):
        raise BodyCreateError("INVALID_ARGUMENT", "body_name must be a string")
    if not body_name.strip():
        raise BodyCreateError("INVALID_ARGUMENT", "body_name must not be empty")
    if doc.getObject(body_name) is not None:
        raise BodyCreateError(
            "OBJECT_ALREADY_EXISTS",
            f"Object already exists: {body_name!r}",
        )

    body = doc.addObject("PartDesign::Body", body_name)
    return BodyCreateReceipt(name=body.Name, body=body)


def _is_partdesign_body(body: BodyObject) -> bool:
    try:
        return bool(body.isDerivedFrom("PartDesign::Body"))
    except (AttributeError, TypeError):
        return body.TypeId == "PartDesign::Body"


def read_body_result(doc: BodyReadDocument, receipt: BodyCreateReceipt) -> BodyCreateInspection:
    """Build the public result after the shared mutation recompute."""

    body = doc.getObject(receipt.name)
    if body is None:
        raise BodyCreateError(
            "CREATED_OBJECT_MISSING",
            f"Created body is missing: {receipt.name!r}",
        )
    if body is not receipt.body:
        raise BodyCreateError(
            "CREATED_OBJECT_REPLACED",
            f"Created body was replaced before commit: {receipt.name!r}",
        )
    if not _is_partdesign_body(body):
        raise BodyCreateError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Created object is not a PartDesign::Body: {receipt.name!r}",
        )
    return BodyCreateInspection(
        name=BodyName(receipt.name),
        label=str(body.Label),
    )


def build_body_create_request(
    doc_name: object, body_name: object
) -> BodyCreateRequest | BodyCreateFailure:
    """Validate the untyped JSON arguments before constructing internal name types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(BodyCreateError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(body_name, str) or not body_name.strip():
        return _failure(BodyCreateError("INVALID_ARGUMENT", "body_name must be a nonempty string"))
    return BodyCreateRequest(
        doc_name=DocumentName(doc_name),
        body_name=BodyName(body_name),
    )


@dataclass(slots=True)
class _BodyCreateExecution:
    collaborators: BodyCreateCollaborators
    request: BodyCreateRequest
    created: BodyCreateReceipt | None = None
    inspected: BodyCreateInspection | None = None

    def apply(self, doc: BodyDocument) -> None:
        self.created = apply_body_create(doc, self.request.body_name)

    def inspect(self, doc: BodyReadDocument) -> None:
        if self.created is None:
            raise BodyCreateError(
                "INVALID_BODY_CREATE_RESULT",
                "Body creation did not return an identity receipt",
            )
        self.inspected = read_body_result(doc, self.created)

    def run(self) -> BodyCreateResult:
        result = run_body_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_body_create_uncertain(
                "BODY_CREATE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected Body result",
                committed=True,
            )
        return make_body_create_success(self.inspected.name, self.inspected.label)


def run_body_create(
    collaborators: BodyCreateCollaborators,
    doc_name: object,
    body_name: object,
) -> BodyCreateResult:
    """Run Body creation through apply, recompute, inspection, and commit."""

    request = build_body_create_request(doc_name, body_name)
    if isinstance(request, dict):
        return request
    return _BodyCreateExecution(collaborators, request).run()


class _BodyCreateRpcFacade(Protocol):
    _cad_collaborators: BodyCreateCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_body_create(
    self: _BodyCreateRpcFacade,
    doc_name: str,
    body_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_body_create(collaborators, doc_name, body_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("body_create", rpc_body_create)


__all__ = [
    "BodyCreateCollaborators",
    "BodyCreateError",
    "BodyCreateInspection",
    "BodyCreateReceipt",
    "apply_body_create",
    "build_body_create_request",
    "read_body_result",
    "rpc_body_create",
    "run_body_create",
    "TYPED_RPC_HANDLER",
]
