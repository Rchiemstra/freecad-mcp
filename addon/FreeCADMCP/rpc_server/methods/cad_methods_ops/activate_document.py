"""Typed ``activate_document`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.activate_document_contract import (
    ActivateDocumentCollaborators,
    ActivateDocumentFailure,
    ActivateDocumentRequest,
    ActivateDocumentResult,
    DocumentName,
    make_activate_document_failure,
    make_activate_document_success,
    make_activate_document_uncertain,
)
from .activate_document_mutation import ActivateDocumentError, run_activate_document_native_mutation
from .typed_rpc_document import document_name


@dataclass(frozen=True, slots=True)
class ActivateDocumentReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    label: str


@dataclass(frozen=True, slots=True)
class ActivateDocumentInspection:
    """Read-only data captured after the native-owned recompute."""

    name: DocumentName
    label: str


def _failure(error: ActivateDocumentError, *, retry_safe: bool = True) -> ActivateDocumentFailure:
    return make_activate_document_failure(
        error.code, str(error), retry_safe=retry_safe, diagnostics=error.diagnostics
    )


def apply_activate_document(doc: object, request: ActivateDocumentRequest) -> ActivateDocumentReceipt:
    """Apply activate_document without recomputing or managing a transaction."""

    return ActivateDocumentReceipt(
        name=document_name(doc),
        label=str(getattr(doc, "Label", document_name(doc))),
    )


def read_activate_document_result(doc: object, receipt: ActivateDocumentReceipt) -> ActivateDocumentInspection:
    """Build the public result after the shared mutation recompute."""

    if document_name(doc) != receipt.name:
        raise ActivateDocumentError(
            "DOCUMENT_IDENTITY_MISMATCH",
            "Inspected document name does not match the apply receipt",
        )
    return ActivateDocumentInspection(
        name=DocumentName(receipt.name),
        label=receipt.label,
    )


def build_activate_document_request(doc_name: object) -> ActivateDocumentRequest | ActivateDocumentFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(ActivateDocumentError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    return ActivateDocumentRequest(doc_name=DocumentName(doc_name))


@dataclass(slots=True)
class _ActivateDocumentExecution:
    collaborators: ActivateDocumentCollaborators
    request: ActivateDocumentRequest
    created: ActivateDocumentReceipt | None = None
    inspected: ActivateDocumentInspection | None = None

    def apply(self, doc: object) -> None:
        self.created = apply_activate_document(doc, self.request)

    def inspect(self, doc: object) -> None:
        if self.created is None:
            raise ActivateDocumentError(
                "INVALID_ACTIVATE_DOCUMENT_RESULT",
                "activate_document did not return an identity receipt",
            )
        self.inspected = read_activate_document_result(doc, self.created)

    def run(self) -> ActivateDocumentResult:
        result = run_activate_document_native_mutation(
            self.collaborators,
            str(getattr(self.request, "doc_name", getattr(self.request, "name", ""))),
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_activate_document_uncertain(
                "ACTIVATE_DOCUMENT_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected activate_document result",
                committed=True,
            )
        return make_activate_document_success(self.inspected.name, self.inspected.label)


def run_activate_document(
    collaborators: ActivateDocumentCollaborators,
    doc_name: object,
) -> ActivateDocumentResult:
    """Run activate_document through apply, recompute, inspection, and commit."""

    request = build_activate_document_request(doc_name)
    if isinstance(request, dict):
        return request
    result = _ActivateDocumentExecution(collaborators, request).run()
    if not (isinstance(result, dict) and result.get("success") is True):
        return result
    app = getattr(collaborators, "freecad", None)
    setter = getattr(app, "setActiveDocument", None)
    if not callable(setter):
        return make_activate_document_uncertain(
            "ACTIVATE_DOCUMENT_FAILED",
            "Native commit succeeded but FreeCAD cannot activate documents",
            committed=True,
        )
    try:
        setter(str(request.doc_name))
    except Exception as exc:
        return make_activate_document_uncertain(
            "ACTIVATE_DOCUMENT_FAILED",
            str(exc) or type(exc).__name__,
            committed=True,
        )
    return result


class _ActivateDocumentRpcFacade(Protocol):
    _cad_collaborators: ActivateDocumentCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_activate_document(
    self: _ActivateDocumentRpcFacade,
    doc_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_activate_document(collaborators, doc_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("activate_document", rpc_activate_document)


__all__ = [
    "ActivateDocumentCollaborators",
    "ActivateDocumentError",
    "ActivateDocumentInspection",
    "ActivateDocumentReceipt",
    "apply_activate_document",
    "build_activate_document_request",
    "read_activate_document_result",
    "rpc_activate_document",
    "run_activate_document",
    "TYPED_RPC_HANDLER",
]
