"""Typed ``undo`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.undo_contract import (
    UndoCollaborators,
    UndoFailure,
    UndoRequest,
    UndoResult,
    DocumentName,
    make_undo_failure,
    make_undo_success,
    make_undo_uncertain,
)
from .undo_mutation import UndoError, run_undo_native_mutation
from .typed_rpc_document import document_name


@dataclass(frozen=True, slots=True)
class UndoReceipt:
    """Internal identity captured while applying the mutation."""

    name: str


@dataclass(frozen=True, slots=True)
class UndoInspection:
    """Read-only data captured after the native-owned recompute."""

    name: DocumentName


def _failure(error: UndoError, *, retry_safe: bool = True) -> UndoFailure:
    return make_undo_failure(
        error.code, str(error), retry_safe=retry_safe, diagnostics=error.diagnostics
    )


def apply_undo(doc: object, request: UndoRequest) -> UndoReceipt:
    """Apply undo without recomputing or managing a transaction."""

    action = getattr(doc, "undo", None)
    if not callable(action):
        raise UndoError("INVALID_DOCUMENT", "document cannot undo")
    action()
    return UndoReceipt(name=document_name(doc))


def read_undo_result(doc: object, receipt: UndoReceipt) -> UndoInspection:
    """Build the public result after the shared mutation recompute."""

    if document_name(doc) != receipt.name:
        raise UndoError(
            "DOCUMENT_IDENTITY_MISMATCH",
            "Inspected document name does not match the apply receipt",
        )
    return UndoInspection(
        name=DocumentName(receipt.name)
    )


def build_undo_request(doc_name: object) -> UndoRequest | UndoFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(UndoError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    return UndoRequest(doc_name=DocumentName(doc_name))


@dataclass(slots=True)
class _UndoExecution:
    collaborators: UndoCollaborators
    request: UndoRequest
    created: UndoReceipt | None = None
    inspected: UndoInspection | None = None

    def apply(self, doc: object) -> None:
        self.created = apply_undo(doc, self.request)

    def inspect(self, doc: object) -> None:
        if self.created is None:
            raise UndoError(
                "INVALID_UNDO_RESULT",
                "undo did not return an identity receipt",
            )
        self.inspected = read_undo_result(doc, self.created)

    def run(self) -> UndoResult:
        result = run_undo_native_mutation(
            self.collaborators,
            str(getattr(self.request, "doc_name", getattr(self.request, "name", ""))),
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_undo_uncertain(
                "UNDO_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected undo result",
                committed=True,
            )
        return make_undo_success(self.inspected.name)


def run_undo(
    collaborators: UndoCollaborators,
    doc_name: object,
) -> UndoResult:
    """Run undo through apply, recompute, inspection, and commit."""

    request = build_undo_request(doc_name)
    if isinstance(request, dict):
        return request
    return _UndoExecution(collaborators, request).run()


class _UndoRpcFacade(Protocol):
    _cad_collaborators: UndoCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_undo(
    self: _UndoRpcFacade,
    doc_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_undo(collaborators, doc_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("undo", rpc_undo)


__all__ = [
    "UndoCollaborators",
    "UndoError",
    "UndoInspection",
    "UndoReceipt",
    "apply_undo",
    "build_undo_request",
    "read_undo_result",
    "rpc_undo",
    "run_undo",
    "TYPED_RPC_HANDLER",
]
