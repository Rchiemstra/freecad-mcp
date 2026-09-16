"""Typed ``close_document`` lifecycle handler."""

from __future__ import annotations

from collections.abc import Callable
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
from .policy_runtime import app_from, lookup_document


class CloseDocumentError(RuntimeError):
    def __init__(self, code: str, message: str, diagnostics: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.diagnostics = diagnostics


def _failure(error: CloseDocumentError, *, retry_safe: bool = True) -> CloseDocumentFailure:
    return make_close_document_failure(
        error.code, str(error), retry_safe=retry_safe, diagnostics=error.diagnostics
    )


def build_close_document_request(
    doc_name: object,
) -> CloseDocumentRequest | CloseDocumentFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(
            CloseDocumentError("INVALID_ARGUMENT", "doc_name must be a nonempty string")
        )
    return CloseDocumentRequest(doc_name=DocumentName(doc_name))


def prepare_close_document(app: object, request: CloseDocumentRequest) -> CloseDocumentFailure | None:
    if lookup_document(app, str(request.doc_name)) is None:
        return _failure(CloseDocumentError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}"))
    return None


def perform_close_document(app: object, request: CloseDocumentRequest) -> CloseDocumentFailure | None:
    closer = getattr(app, "closeDocument", None)
    if not callable(closer):
        return _failure(CloseDocumentError("FREECAD_UNAVAILABLE", "FreeCAD cannot close documents"))
    try:
        closer(str(request.doc_name))
    except Exception as exc:
        return _failure(CloseDocumentError("CLOSE_DOCUMENT_FAILED", str(exc) or type(exc).__name__))
    return None


def verify_close_document(app: object, request: CloseDocumentRequest) -> CloseDocumentResult | None:
    if lookup_document(app, str(request.doc_name)) is None:
        return make_close_document_success(DocumentName(str(request.doc_name)))
    return None


def run_close_document(
    collaborators: CloseDocumentCollaborators,
    doc_name: object,
) -> CloseDocumentResult:
    request = build_close_document_request(doc_name)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(CloseDocumentError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    prep = prepare_close_document(app, request)
    if prep is not None:
        return prep
    perf = perform_close_document(app, request)
    if perf is not None:
        return perf
    verified = verify_close_document(app, request)
    if verified is not None:
        return verified
    return make_close_document_uncertain(
        "DOCUMENT_CLOSE_REJECTED",
        f"FreeCAD did not close document {request.doc_name!r}",
        committed=None,
    )


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
    "build_close_document_request",
    "rpc_close_document",
    "run_close_document",
    "TYPED_RPC_HANDLER",
]
