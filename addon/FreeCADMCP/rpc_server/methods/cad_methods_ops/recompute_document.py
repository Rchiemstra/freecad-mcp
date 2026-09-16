"""Typed ``recompute_document`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.recompute_document_contract import (
    RecomputeDocumentCollaborators,
    RecomputeDocumentFailure,
    RecomputeDocumentRequest,
    RecomputeDocumentResult,
    DocumentName,
    make_recompute_document_failure,
    make_recompute_document_success,
    make_recompute_document_uncertain,
)
from .recompute_document_mutation import RecomputeDocumentError, run_recompute_document_native_mutation
from .typed_rpc_document import document_name


@dataclass(frozen=True, slots=True)
class RecomputeDocumentReceipt:
    """Internal identity captured while applying the mutation."""

    name: str


@dataclass(frozen=True, slots=True)
class RecomputeDocumentInspection:
    """Read-only data captured after the native-owned recompute."""

    name: DocumentName


def _failure(error: RecomputeDocumentError, *, retry_safe: bool = True) -> RecomputeDocumentFailure:
    return make_recompute_document_failure(
        error.code, str(error), retry_safe=retry_safe, diagnostics=error.diagnostics
    )


def apply_recompute_document(doc: object, request: RecomputeDocumentRequest) -> RecomputeDocumentReceipt:
    """Apply recompute_document without recomputing or managing a transaction."""

    return RecomputeDocumentReceipt(name=document_name(doc))


def read_recompute_document_result(doc: object, receipt: RecomputeDocumentReceipt) -> RecomputeDocumentInspection:
    """Build the public result after the shared mutation recompute."""

    if document_name(doc) != receipt.name:
        raise RecomputeDocumentError(
            "DOCUMENT_IDENTITY_MISMATCH",
            "Inspected document name does not match the apply receipt",
        )
    return RecomputeDocumentInspection(
        name=DocumentName(receipt.name)
    )


def build_recompute_document_request(doc_name: object) -> RecomputeDocumentRequest | RecomputeDocumentFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(RecomputeDocumentError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    return RecomputeDocumentRequest(doc_name=DocumentName(doc_name))


@dataclass(slots=True)
class _RecomputeDocumentExecution:
    collaborators: RecomputeDocumentCollaborators
    request: RecomputeDocumentRequest
    created: RecomputeDocumentReceipt | None = None
    inspected: RecomputeDocumentInspection | None = None

    def apply(self, doc: object) -> None:
        self.created = apply_recompute_document(doc, self.request)

    def inspect(self, doc: object) -> None:
        if self.created is None:
            raise RecomputeDocumentError(
                "INVALID_RECOMPUTE_DOCUMENT_RESULT",
                "recompute_document did not return an identity receipt",
            )
        self.inspected = read_recompute_document_result(doc, self.created)

    def run(self) -> RecomputeDocumentResult:
        result = run_recompute_document_native_mutation(
            self.collaborators,
            str(getattr(self.request, "doc_name", getattr(self.request, "name", ""))),
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_recompute_document_uncertain(
                "RECOMPUTE_DOCUMENT_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected recompute_document result",
                committed=True,
            )
        return make_recompute_document_success(self.inspected.name)


def run_recompute_document(
    collaborators: RecomputeDocumentCollaborators,
    doc_name: object,
) -> RecomputeDocumentResult:
    """Run recompute_document through apply, recompute, inspection, and commit."""

    request = build_recompute_document_request(doc_name)
    if isinstance(request, dict):
        return request
    return _RecomputeDocumentExecution(collaborators, request).run()


class _RecomputeDocumentRpcFacade(Protocol):
    _cad_collaborators: RecomputeDocumentCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_recompute_document(
    self: _RecomputeDocumentRpcFacade,
    doc_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_recompute_document(collaborators, doc_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("recompute_document", rpc_recompute_document)


__all__ = [
    "RecomputeDocumentCollaborators",
    "RecomputeDocumentError",
    "RecomputeDocumentInspection",
    "RecomputeDocumentReceipt",
    "apply_recompute_document",
    "build_recompute_document_request",
    "read_recompute_document_result",
    "rpc_recompute_document",
    "run_recompute_document",
    "TYPED_RPC_HANDLER",
]
