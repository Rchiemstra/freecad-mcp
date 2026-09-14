"""Typed ``reload_document`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.reload_document_contract import (
    DocumentName,
    ReloadDocumentCollaborators,
    ReloadDocumentFailure,
    ReloadDocumentRequest,
    ReloadDocumentResult,
    make_reload_document_failure,
    make_reload_document_success,
    make_reload_document_uncertain,
)
from .reload_document_mutation import ReloadDocumentError, run_reload_document_native_mutation
from .typed_rpc_document import document_name


@dataclass(frozen=True, slots=True)
class ReloadDocumentReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    file_name: str | None


@dataclass(frozen=True, slots=True)
class ReloadDocumentInspection:
    """Read-only data captured after the native-owned recompute."""

    name: DocumentName


def _failure(error: ReloadDocumentError, *, retry_safe: bool = True) -> ReloadDocumentFailure:
    return make_reload_document_failure(
        error.code, str(error), retry_safe=retry_safe, diagnostics=error.diagnostics
    )


def apply_reload_document(doc: object, request: ReloadDocumentRequest) -> ReloadDocumentReceipt:
    """Capture identity before the post-commit reload."""

    file_name = getattr(doc, "FileName", None)
    return ReloadDocumentReceipt(
        name=document_name(doc) or str(request.doc_name),
        file_name=file_name if isinstance(file_name, str) and file_name.strip() else None,
    )


def read_reload_document_result(
    doc: object, receipt: ReloadDocumentReceipt
) -> ReloadDocumentInspection:
    """Confirm the admitted document is present before the post-commit reload."""

    return ReloadDocumentInspection(name=DocumentName(document_name(doc) or receipt.name))


def build_reload_document_request(
    doc_name: object,
) -> ReloadDocumentRequest | ReloadDocumentFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(
            ReloadDocumentError("INVALID_ARGUMENT", "doc_name must be a nonempty string")
        )
    return ReloadDocumentRequest(doc_name=DocumentName(doc_name))


@dataclass(slots=True)
class _ReloadDocumentExecution:
    collaborators: ReloadDocumentCollaborators
    request: ReloadDocumentRequest
    created: ReloadDocumentReceipt | None = None
    inspected: ReloadDocumentInspection | None = None

    def apply(self, doc: object) -> None:
        self.created = apply_reload_document(doc, self.request)

    def inspect(self, doc: object) -> None:
        if self.created is None:
            raise ReloadDocumentError(
                "INVALID_RELOAD_DOCUMENT_RESULT",
                "Document reload did not return an identity receipt",
            )
        self.inspected = read_reload_document_result(doc, self.created)

    def run(self) -> ReloadDocumentResult:
        result = run_reload_document_native_mutation(
            self.collaborators,
            str(self.request.doc_name),
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_reload_document_uncertain(
                "RELOAD_DOCUMENT_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected reload_document result",
                committed=True,
            )
        return make_reload_document_success(self.inspected.name)


def run_reload_document(
    collaborators: ReloadDocumentCollaborators,
    doc_name: object,
) -> ReloadDocumentResult:
    """Seal document health natively, then reload from disk."""

    request = build_reload_document_request(doc_name)
    if isinstance(request, dict):
        return request
    execution = _ReloadDocumentExecution(collaborators, request)
    result = execution.run()
    if not (isinstance(result, dict) and result.get("success") is True):
        return result
    receipt = execution.created
    app = getattr(collaborators, "freecad", None)
    if receipt is None or receipt.file_name is None:
        return make_reload_document_uncertain(
            "RELOAD_DOCUMENT_FAILED",
            "Native commit succeeded but the document has no file path to reload",
            committed=True,
        )
    closer = getattr(app, "closeDocument", None)
    opener = getattr(app, "openDocument", None)
    if not callable(closer) or not callable(opener):
        return make_reload_document_uncertain(
            "FREECAD_UNAVAILABLE",
            "Native commit succeeded but FreeCAD cannot reload documents",
            committed=True,
        )
    doc_name = str(request.doc_name)
    try:
        closer(doc_name)
    except NameError:
        pass
    except Exception as exc:
        return make_reload_document_uncertain(
            "RELOAD_DOCUMENT_FAILED",
            str(exc) or type(exc).__name__,
            committed=True,
        )
    try:
        reopened = opener(receipt.file_name)
    except Exception as exc:
        return make_reload_document_uncertain(
            "RELOAD_DOCUMENT_FAILED",
            str(exc) or type(exc).__name__,
            committed=True,
        )
    if reopened is None:
        return make_reload_document_uncertain(
            "RELOAD_DOCUMENT_FAILED",
            f"FreeCAD did not reopen {receipt.file_name!r}",
            committed=True,
        )
    try:
        reopened_name = document_name(reopened)
    except NameError:
        reopened_name = doc_name
    if not reopened_name:
        return make_reload_document_uncertain(
            "RELOAD_DOCUMENT_FAILED",
            f"FreeCAD reopened {receipt.file_name!r} without a document name",
            committed=True,
        )
    return make_reload_document_success(DocumentName(reopened_name))


class _ReloadDocumentRpcFacade(Protocol):
    _cad_collaborators: ReloadDocumentCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_reload_document(self: _ReloadDocumentRpcFacade, doc_name: str) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_reload_document(collaborators, doc_name))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("reload_document", rpc_reload_document)


__all__ = [
    "ReloadDocumentCollaborators",
    "ReloadDocumentError",
    "ReloadDocumentInspection",
    "ReloadDocumentReceipt",
    "apply_reload_document",
    "build_reload_document_request",
    "read_reload_document_result",
    "rpc_reload_document",
    "run_reload_document",
    "TYPED_RPC_HANDLER",
]
