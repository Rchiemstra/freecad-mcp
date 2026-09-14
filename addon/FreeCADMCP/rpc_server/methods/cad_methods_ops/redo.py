"""Typed ``redo`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.redo_contract import (
    RedoCollaborators,
    RedoFailure,
    RedoRequest,
    RedoResult,
    DocumentName,
    make_redo_failure,
    make_redo_success,
    make_redo_uncertain,
)
from .redo_mutation import RedoError, run_redo_native_mutation
from .typed_rpc_document import document_name


@dataclass(frozen=True, slots=True)
class RedoReceipt:
    """Internal identity captured while applying the mutation."""

    name: str


@dataclass(frozen=True, slots=True)
class RedoInspection:
    """Read-only data captured after the native-owned recompute."""

    name: DocumentName


def _failure(error: RedoError, *, retry_safe: bool = True) -> RedoFailure:
    return make_redo_failure(
        error.code, str(error), retry_safe=retry_safe, diagnostics=error.diagnostics
    )


def apply_redo(doc: object, request: RedoRequest) -> RedoReceipt:
    """Apply redo without recomputing or managing a transaction."""

    action = getattr(doc, "redo", None)
    if not callable(action):
        raise RedoError("INVALID_DOCUMENT", "document cannot redo")
    action()
    return RedoReceipt(name=document_name(doc))


def read_redo_result(doc: object, receipt: RedoReceipt) -> RedoInspection:
    """Build the public result after the shared mutation recompute."""

    if document_name(doc) != receipt.name:
        raise RedoError(
            "DOCUMENT_IDENTITY_MISMATCH",
            "Inspected document name does not match the apply receipt",
        )
    return RedoInspection(
        name=DocumentName(receipt.name)
    )


def build_redo_request(doc_name: object) -> RedoRequest | RedoFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(RedoError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    return RedoRequest(doc_name=DocumentName(doc_name))


@dataclass(slots=True)
class _RedoExecution:
    collaborators: RedoCollaborators
    request: RedoRequest
    created: RedoReceipt | None = None
    inspected: RedoInspection | None = None

    def apply(self, doc: object) -> None:
        self.created = apply_redo(doc, self.request)

    def inspect(self, doc: object) -> None:
        if self.created is None:
            raise RedoError(
                "INVALID_REDO_RESULT",
                "redo did not return an identity receipt",
            )
        self.inspected = read_redo_result(doc, self.created)

    def run(self) -> RedoResult:
        result = run_redo_native_mutation(
            self.collaborators,
            str(getattr(self.request, "doc_name", getattr(self.request, "name", ""))),
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_redo_uncertain(
                "REDO_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected redo result",
                committed=True,
            )
        return make_redo_success(self.inspected.name)


def run_redo(
    collaborators: RedoCollaborators,
    doc_name: object,
) -> RedoResult:
    """Run redo through apply, recompute, inspection, and commit."""

    request = build_redo_request(doc_name)
    if isinstance(request, dict):
        return request
    return _RedoExecution(collaborators, request).run()


class _RedoRpcFacade(Protocol):
    _cad_collaborators: RedoCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_redo(
    self: _RedoRpcFacade,
    doc_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_redo(collaborators, doc_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("redo", rpc_redo)


__all__ = [
    "RedoCollaborators",
    "RedoError",
    "RedoInspection",
    "RedoReceipt",
    "apply_redo",
    "build_redo_request",
    "read_redo_result",
    "rpc_redo",
    "run_redo",
    "TYPED_RPC_HANDLER",
]
