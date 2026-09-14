"""Typed ``close_document`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.close_document_contract import (
    CloseDocumentCollaborators,
    CloseDocumentFailure,
    CloseDocumentRequest,
    CloseDocumentResult,
    DocumentName,
    make_close_document_failure,
    make_close_document_success,
    make_close_document_uncertain,
)
from .close_document_mutation import CloseDocumentError, run_close_document_native_mutation
from .typed_rpc_document import document_name


@dataclass(frozen=True, slots=True)
class CloseDocumentReceipt:
    """Internal identity captured while applying the mutation."""

    name: str


@dataclass(frozen=True, slots=True)
class CloseDocumentInspection:
    """Read-only data captured after the native-owned recompute."""

    name: DocumentName


def _failure(error: CloseDocumentError, *, retry_safe: bool = True) -> CloseDocumentFailure:
    return make_close_document_failure(
        error.code, str(error), retry_safe=retry_safe, diagnostics=error.diagnostics
    )


def apply_close_document(doc: object, request: CloseDocumentRequest) -> CloseDocumentReceipt:
    """Record the document identity; closing happens after native commit."""

    return CloseDocumentReceipt(name=document_name(doc) or str(request.doc_name))


def read_close_document_result(
    doc: object, receipt: CloseDocumentReceipt
) -> CloseDocumentInspection:
    """Confirm the admitted document is still present before the post-commit close."""

    name = document_name(doc)
    if name != receipt.name:
        raise CloseDocumentError(
            "DOCUMENT_IDENTITY_MISMATCH",
            f"Close inspection saw {name!r} instead of {receipt.name!r}",
        )
    return CloseDocumentInspection(name=DocumentName(name))


def build_close_document_request(
    doc_name: object,
) -> CloseDocumentRequest | CloseDocumentFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(
            CloseDocumentError("INVALID_ARGUMENT", "doc_name must be a nonempty string")
        )
    return CloseDocumentRequest(doc_name=DocumentName(doc_name))


@dataclass(slots=True)
class _CloseDocumentExecution:
    collaborators: CloseDocumentCollaborators
    request: CloseDocumentRequest
    created: CloseDocumentReceipt | None = None
    inspected: CloseDocumentInspection | None = None

    def apply(self, doc: object) -> None:
        self.created = apply_close_document(doc, self.request)

    def inspect(self, doc: object) -> None:
        if self.created is None:
            raise CloseDocumentError(
                "INVALID_CLOSE_DOCUMENT_RESULT",
                "Document close did not return an identity receipt",
            )
        self.inspected = read_close_document_result(doc, self.created)

    def run(self) -> CloseDocumentResult:
        result = run_close_document_native_mutation(
            self.collaborators,
            str(self.request.doc_name),
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_close_document_uncertain(
                "CLOSE_DOCUMENT_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected close_document result",
                committed=True,
            )
        return make_close_document_success(self.inspected.name)


def run_close_document(
    collaborators: CloseDocumentCollaborators,
    doc_name: object,
) -> CloseDocumentResult:
    """Seal document health natively, then close the admitted document."""

    request = build_close_document_request(doc_name)
    if isinstance(request, dict):
        return request
    result = _CloseDocumentExecution(collaborators, request).run()
    if not (isinstance(result, dict) and result.get("success") is True):
        return result
    app = getattr(collaborators, "freecad", None)
    closer = getattr(app, "closeDocument", None)
    if not callable(closer):
        return make_close_document_uncertain(
            "CLOSE_DOCUMENT_FAILED",
            "Native commit succeeded but FreeCAD cannot close documents",
            committed=True,
        )
    try:
        closer(str(request.doc_name))
    except Exception as exc:
        return make_close_document_uncertain(
            "CLOSE_DOCUMENT_FAILED",
            str(exc) or type(exc).__name__,
            committed=True,
        )
    remaining = getattr(app, "getDocument", None)
    if callable(remaining) and remaining(str(request.doc_name)) is not None:
        return make_close_document_uncertain(
            "DOCUMENT_CLOSE_REJECTED",
            f"FreeCAD did not close document {request.doc_name!r}",
            committed=True,
        )
    return result


class _CloseDocumentRpcFacade(Protocol):
    _cad_collaborators: CloseDocumentCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_close_document(self: _CloseDocumentRpcFacade, doc_name: str) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_close_document(collaborators, doc_name))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("close_document", rpc_close_document)


__all__ = [
    "CloseDocumentCollaborators",
    "CloseDocumentError",
    "CloseDocumentInspection",
    "CloseDocumentReceipt",
    "apply_close_document",
    "build_close_document_request",
    "read_close_document_result",
    "rpc_close_document",
    "run_close_document",
    "TYPED_RPC_HANDLER",
]
