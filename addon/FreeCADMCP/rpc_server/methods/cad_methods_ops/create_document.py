"""Typed ``create_document`` lifecycle handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ...._shared.protocol.create_document_contract import (
    CreateDocumentCollaborators,
    CreateDocumentFailure,
    CreateDocumentRequest,
    CreateDocumentResult,
    DocumentName,
    make_create_document_compensated,
    make_create_document_failure,
    make_create_document_success,
    make_create_document_uncertain,
)
from .policy_runtime import app_from, lookup_document


class CreateDocumentError(RuntimeError):
    """An operation failure with a stable wire code."""

    def __init__(self, code: str, message: str, diagnostics: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.diagnostics = diagnostics


def _failure(error: CreateDocumentError, *, retry_safe: bool = True) -> CreateDocumentFailure:
    return make_create_document_failure(
        error.code, str(error), retry_safe=retry_safe, diagnostics=error.diagnostics
    )


def _app_call(app: object, method: str, *args: object) -> object:
    func = getattr(app, method, None)
    if not callable(func):
        raise CreateDocumentError("FREECAD_UNAVAILABLE", f"FreeCAD is missing {method}")
    return func(*args)


def build_create_document_request(
    name: object,
) -> CreateDocumentRequest | CreateDocumentFailure:
    if not isinstance(name, str) or not name.strip():
        return _failure(
            CreateDocumentError("INVALID_ARGUMENT", "name must be a nonempty string")
        )
    return CreateDocumentRequest(name=DocumentName(name))


def prepare_create_document(app: object, request: CreateDocumentRequest) -> CreateDocumentFailure | None:
    if lookup_document(app, str(request.name)) is not None:
        return _failure(
            CreateDocumentError(
                "DOCUMENT_ALREADY_EXISTS",
                f"Document already exists: {request.name!r}",
            ),
            retry_safe=False,
        )
    return None


def perform_create_document(app: object, request: CreateDocumentRequest) -> CreateDocumentFailure | None:
    try:
        _app_call(app, "newDocument", str(request.name))
    except CreateDocumentError as exc:
        return _failure(exc)
    except Exception as exc:
        return _failure(
            CreateDocumentError("CREATE_DOCUMENT_FAILED", str(exc) or type(exc).__name__)
        )
    return None


def verify_create_document(
    app: object, request: CreateDocumentRequest
) -> CreateDocumentResult | None:
    document = lookup_document(app, str(request.name))
    if document is None:
        return None
    return make_create_document_success(DocumentName(str(request.name)))


def compensate_create_document(app: object, request: CreateDocumentRequest) -> CreateDocumentResult:
    try:
        _app_call(app, "closeDocument", str(request.name))
    except Exception as exc:
        return make_create_document_uncertain(
            "CREATE_DOCUMENT_ROLLBACK_UNCERTAIN",
            str(exc) or type(exc).__name__,
            committed=None,
        )
    if lookup_document(app, str(request.name)) is not None:
        return make_create_document_uncertain(
            "CREATE_DOCUMENT_ROLLBACK_UNCERTAIN",
            f"Document {request.name!r} could not be closed after a failed create",
            committed=None,
        )
    return make_create_document_compensated(
        "CREATE_DOCUMENT_FAILED",
        f"Document creation for {request.name!r} failed and was rolled back",
    )


def run_create_document(
    collaborators: CreateDocumentCollaborators,
    name: object,
) -> CreateDocumentResult:
    request = build_create_document_request(name)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(CreateDocumentError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    prep = prepare_create_document(app, request)
    if prep is not None:
        return prep
    perf = perform_create_document(app, request)
    if perf is not None:
        if lookup_document(app, str(request.name)) is None:
            return perf
        return compensate_create_document(app, request)
    verified = verify_create_document(app, request)
    if verified is not None:
        return verified
    return compensate_create_document(app, request)


class _CreateDocumentRpcFacade(Protocol):
    _cad_collaborators: CreateDocumentCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_create_document(
    self: _CreateDocumentRpcFacade,
    name: str = "New_Document",
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_create_document(collaborators, name))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("create_document", rpc_create_document)


__all__ = [
    "CreateDocumentCollaborators",
    "CreateDocumentError",
    "build_create_document_request",
    "compensate_create_document",
    "perform_create_document",
    "prepare_create_document",
    "rpc_create_document",
    "run_create_document",
    "verify_create_document",
    "TYPED_RPC_HANDLER",
]
