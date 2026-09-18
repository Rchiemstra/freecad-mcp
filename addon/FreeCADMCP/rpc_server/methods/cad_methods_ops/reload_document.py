"""Typed ``reload_document`` lifecycle handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

try:
    from ...._shared.protocol.reload_document_contract import (
        DocumentName,
        ReloadDocumentCollaborators,
        ReloadDocumentFailure,
        ReloadDocumentRequest,
        ReloadDocumentResult,
        ReloadDocumentUncertain,
        make_reload_document_failure,
        make_reload_document_success,
        make_reload_document_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.reload_document_contract import (
        DocumentName,
        ReloadDocumentCollaborators,
        ReloadDocumentFailure,
        ReloadDocumentRequest,
        ReloadDocumentResult,
        ReloadDocumentUncertain,
        make_reload_document_failure,
        make_reload_document_success,
        make_reload_document_uncertain,
    )
from .policy_runtime import app_from, lookup_document
from .typed_rpc_document import document_name


class ReloadDocumentError(RuntimeError):
    def __init__(self, code: str, message: str, diagnostics: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.diagnostics = diagnostics


def _failure(error: ReloadDocumentError, *, retry_safe: bool = True) -> ReloadDocumentFailure:
    return make_reload_document_failure(
        error.code, str(error), retry_safe=retry_safe, diagnostics=error.diagnostics
    )


def build_reload_document_request(
    doc_name: object,
) -> ReloadDocumentRequest | ReloadDocumentFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(
            ReloadDocumentError("INVALID_ARGUMENT", "doc_name must be a nonempty string")
        )
    return ReloadDocumentRequest(doc_name=DocumentName(doc_name))


def prepare_reload_document(
    app: object, request: ReloadDocumentRequest
) -> tuple[ReloadDocumentFailure | None, str | None]:
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(
            ReloadDocumentError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}")
        ), None
    file_name = getattr(document, "FileName", None)
    if not isinstance(file_name, str) or not file_name.strip():
        return _failure(
            ReloadDocumentError("RELOAD_DOCUMENT_FAILED", "Document has no file path to reload")
        ), None
    return None, file_name


def perform_reload_document(
    app: object, request: ReloadDocumentRequest, file_name: str
) -> tuple[ReloadDocumentFailure | ReloadDocumentUncertain | None, str | None]:
    closer = getattr(app, "closeDocument", None)
    opener = getattr(app, "openDocument", None)
    if not callable(closer) or not callable(opener):
        return _failure(ReloadDocumentError("FREECAD_UNAVAILABLE", "FreeCAD cannot reload documents")), None
    try:
        closer(str(request.doc_name))
    except NameError:
        pass
    except Exception as exc:
        return _failure(ReloadDocumentError("RELOAD_DOCUMENT_FAILED", str(exc) or type(exc).__name__)), None
    try:
        reopened = opener(file_name)
    except Exception as exc:
        return (
            make_reload_document_uncertain(
                "RELOAD_DOCUMENT_FAILED",
                str(exc) or type(exc).__name__,
                committed=None,
            ),
            None,
        )
    if reopened is None:
        return (
            make_reload_document_uncertain(
                "RELOAD_DOCUMENT_FAILED",
                f"FreeCAD did not reopen {file_name!r}",
                committed=None,
            ),
            None,
        )
    reopened_name = document_name(reopened)
    if not reopened_name:
        return (
            make_reload_document_uncertain(
                "RELOAD_DOCUMENT_FAILED",
                f"FreeCAD reopened {file_name!r} without a document name",
                committed=None,
            ),
            None,
        )
    return None, reopened_name


def verify_reload_document(app: object, reopened_name: str) -> ReloadDocumentResult | None:
    document = lookup_document(app, reopened_name)
    if document is None:
        return None
    name = document_name(document) or reopened_name
    return make_reload_document_success(DocumentName(name))


def run_reload_document(
    collaborators: ReloadDocumentCollaborators,
    doc_name: object,
) -> ReloadDocumentResult:
    request = build_reload_document_request(doc_name)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(ReloadDocumentError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    prep, file_name = prepare_reload_document(app, request)
    if prep is not None or file_name is None:
        return prep if prep is not None else _failure(ReloadDocumentError("RELOAD_DOCUMENT_FAILED", "Reload failed"))
    perf, reopened_name = perform_reload_document(app, request, file_name)
    if perf is not None:
        return perf
    if reopened_name is None:
        return make_reload_document_uncertain(
            "RELOAD_DOCUMENT_FAILED",
            "Reload completed without a reopened document name",
            committed=None,
        )
    verified = verify_reload_document(app, reopened_name)
    if verified is not None:
        return verified
    return make_reload_document_uncertain(
        "RELOAD_DOCUMENT_FAILED",
        f"Document {reopened_name!r} was not present after reload",
        committed=None,
    )


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
    "build_reload_document_request",
    "perform_reload_document",
    "rpc_reload_document",
    "run_reload_document",
    "verify_reload_document",
    "TYPED_RPC_HANDLER",
]
