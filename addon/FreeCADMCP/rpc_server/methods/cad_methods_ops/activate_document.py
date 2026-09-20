"""Typed ``activate_document`` lifecycle handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

try:
    from ...._shared.protocol.activate_document_contract import (
        ActivateDocumentCollaborators,
        ActivateDocumentFailure,
        ActivateDocumentRequest,
        ActivateDocumentResult,
        DocumentName,
        make_activate_document_compensated,
        make_activate_document_failure,
        make_activate_document_success,
        make_activate_document_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.activate_document_contract import (
        ActivateDocumentCollaborators,
        ActivateDocumentFailure,
        ActivateDocumentRequest,
        ActivateDocumentResult,
        DocumentName,
        make_activate_document_compensated,
        make_activate_document_failure,
        make_activate_document_success,
        make_activate_document_uncertain,
    )
from .policy_runtime import app_from, lookup_document
from .typed_rpc_document import document_name


class ActivateDocumentError(RuntimeError):
    def __init__(self, code: str, message: str, diagnostics: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.diagnostics = diagnostics


def _failure(error: ActivateDocumentError, *, retry_safe: bool = True) -> ActivateDocumentFailure:
    return make_activate_document_failure(
        error.code, str(error), retry_safe=retry_safe, diagnostics=error.diagnostics
    )


def build_activate_document_request(
    doc_name: object,
) -> ActivateDocumentRequest | ActivateDocumentFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(ActivateDocumentError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    return ActivateDocumentRequest(doc_name=DocumentName(doc_name))


def prepare_activate_document(
    app: object, request: ActivateDocumentRequest
) -> tuple[ActivateDocumentFailure | None, str | None]:
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(
            ActivateDocumentError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}")
        ), None
    active = getattr(app, "ActiveDocument", None)
    previous = None
    if active is not None:
        previous_name = document_name(active)
        if previous_name and previous_name != str(request.doc_name):
            previous = previous_name
    return None, previous


def perform_activate_document(app: object, request: ActivateDocumentRequest) -> ActivateDocumentFailure | None:
    setter = getattr(app, "setActiveDocument", None)
    if not callable(setter):
        return _failure(ActivateDocumentError("FREECAD_UNAVAILABLE", "FreeCAD cannot activate documents"))
    try:
        setter(str(request.doc_name))
    except Exception as exc:
        return _failure(ActivateDocumentError("ACTIVATE_DOCUMENT_FAILED", str(exc) or type(exc).__name__))
    return None


def verify_activate_document(
    app: object, request: ActivateDocumentRequest
) -> ActivateDocumentResult | None:
    active = getattr(app, "ActiveDocument", None)
    if active is None:
        return None
    active_name = document_name(active)
    if active_name != str(request.doc_name):
        return None
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return None
    label = str(getattr(document, "Label", active_name))
    return make_activate_document_success(DocumentName(active_name), label)


def compensate_activate_document(app: object, previous_active: str | None) -> ActivateDocumentResult:
    if previous_active is None:
        return make_activate_document_compensated(
            "ACTIVATE_DOCUMENT_FAILED",
            "Document activation failed",
        )
    setter = getattr(app, "setActiveDocument", None)
    if not callable(setter):
        return make_activate_document_uncertain(
            "ACTIVATE_DOCUMENT_ROLLBACK_UNCERTAIN",
            "Previous active document could not be restored",
            committed=None,
        )
    try:
        setter(previous_active)
    except Exception as exc:
        return make_activate_document_uncertain(
            "ACTIVATE_DOCUMENT_ROLLBACK_UNCERTAIN",
            str(exc) or type(exc).__name__,
            committed=None,
        )
    return make_activate_document_compensated(
        "ACTIVATE_DOCUMENT_FAILED",
        "Document activation failed and the previous active document was restored",
    )


def run_activate_document(
    collaborators: ActivateDocumentCollaborators,
    doc_name: object,
) -> ActivateDocumentResult:
    request = build_activate_document_request(doc_name)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(ActivateDocumentError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    prep, previous_active = prepare_activate_document(app, request)
    if prep is not None:
        return prep
    perf = perform_activate_document(app, request)
    if perf is not None:
        return perf
    verified = verify_activate_document(app, request)
    if verified is not None:
        return verified
    return compensate_activate_document(app, previous_active)


class _ActivateDocumentRpcFacade(Protocol):
    _cad_collaborators: ActivateDocumentCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_activate_document(
    self: _ActivateDocumentRpcFacade,
    doc_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_activate_document(collaborators, doc_name))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("activate_document", rpc_activate_document)


__all__ = [
    "ActivateDocumentCollaborators",
    "ActivateDocumentError",
    "build_activate_document_request",
    "rpc_activate_document",
    "run_activate_document",
    "TYPED_RPC_HANDLER",
]
