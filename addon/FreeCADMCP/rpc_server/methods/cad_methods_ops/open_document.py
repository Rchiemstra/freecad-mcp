"""Typed ``open_document`` lifecycle handler."""

from __future__ import annotations

import os

from collections.abc import Callable
from typing import Protocol

try:
    from ...._shared.protocol.open_document_contract import (
        DocumentName,
        OpenDocumentCollaborators,
        OpenDocumentFailure,
        OpenDocumentRequest,
        OpenDocumentResult,
        PathName,
        make_open_document_compensated,
        make_open_document_failure,
        make_open_document_success,
        make_open_document_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.open_document_contract import (
        DocumentName,
        OpenDocumentCollaborators,
        OpenDocumentFailure,
        OpenDocumentRequest,
        OpenDocumentResult,
        PathName,
        make_open_document_compensated,
        make_open_document_failure,
        make_open_document_success,
        make_open_document_uncertain,
    )
from .policy_runtime import app_from, lookup_document
from .typed_rpc_document import document_name


class OpenDocumentError(RuntimeError):
    def __init__(self, code: str, message: str, diagnostics: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.diagnostics = diagnostics


def _failure(error: OpenDocumentError, *, retry_safe: bool = True) -> OpenDocumentFailure:
    return make_open_document_failure(
        error.code, str(error), retry_safe=retry_safe, diagnostics=error.diagnostics
    )


def build_open_document_request(path: object) -> OpenDocumentRequest | OpenDocumentFailure:
    if not isinstance(path, str) or not path.strip():
        return _failure(OpenDocumentError("INVALID_ARGUMENT", "path must be a nonempty string"))
    return OpenDocumentRequest(path=PathName(path))


def prepare_open_document(_app: object, request: OpenDocumentRequest) -> OpenDocumentFailure | None:
    if not str(request.path).strip():
        return _failure(OpenDocumentError("INVALID_ARGUMENT", "path must be a nonempty string"))
    if not os.path.isfile(str(request.path)):
        # FreeCAD would raise and log the exception in the Report view.
        return _failure(OpenDocumentError("FILE_NOT_FOUND", f"File does not exist: {str(request.path)!r}"))
    return None


def perform_open_document(app: object, request: OpenDocumentRequest, module: str | None = None) -> tuple[OpenDocumentFailure | None, str | None]:
    extension = os.path.splitext(str(request.path))[1].lower()
    if extension != ".fcstd":
        registry = getattr(app, "getImportType", None)
        modules = list(dict.fromkeys(registry(extension.lstrip(".")) if callable(registry) else []))
        if not modules:
            return _failure(OpenDocumentError("NO_IMPORT_MODULE", f"no import module handles {extension}")), None
        if module is not None and module not in modules:
            return _failure(OpenDocumentError("INVALID_IMPORT_MODULE", f"Choose an import module for {extension}: {', '.join(modules)}")), None
        if module is None and len(modules) != 1:
            return _failure(OpenDocumentError("AMBIGUOUS_IMPORT_MODULE", f"Several import modules handle {extension}: {', '.join(modules)}; pass module to choose")), None
        list_documents = getattr(app, "listDocuments")
        before = set(list_documents())
        try:
            # Module names have been checked against FreeCAD's import registry.
            # Use the external importer entry point, as File > Open does.
            opened = __import__(module or modules[0], fromlist=['open']).open(str(request.path))
        except Exception as exc:
            return _failure(OpenDocumentError("IMPORT_OPEN_FAILED", f"{type(exc).__name__}: {exc}"), retry_safe=False), None
        created = set(list_documents()) - before
        name = getattr(opened, "Name", None)
        if isinstance(name, str) and name:
            return None, name
        if len(created) == 1:
            return None, created.pop()
        return _failure(OpenDocumentError("IMPORT_DOCUMENT_UNRESOLVED", "Import module did not return or create exactly one document"), retry_safe=False), None
    opener = getattr(app, "openDocument", None)
    if not callable(opener):
        return _failure(OpenDocumentError("FREECAD_UNAVAILABLE", "FreeCAD cannot open documents")), None
    try:
        opened = opener(str(request.path))
    except Exception as exc:
        return _failure(OpenDocumentError("OPEN_DOCUMENT_FAILED", str(exc) or type(exc).__name__)), None
    if opened is None:
        return _failure(OpenDocumentError("OPEN_DOCUMENT_FAILED", f"Failed to open: {request.path}")), None
    opened_name = document_name(opened)
    if not opened_name:
        return _failure(OpenDocumentError("OPEN_DOCUMENT_FAILED", "Opened document has no name")), None
    return None, opened_name


def verify_open_document(
    app: object, request: OpenDocumentRequest, opened_name: str
) -> OpenDocumentResult | None:
    document = lookup_document(app, opened_name)
    if document is None:
        return None
    return make_open_document_success(DocumentName(opened_name), str(request.path))


def compensate_open_document(app: object, opened_name: str) -> OpenDocumentResult:
    closer = getattr(app, "closeDocument", None)
    if not callable(closer):
        return make_open_document_uncertain(
            "OPEN_DOCUMENT_ROLLBACK_UNCERTAIN",
            "Opened document could not be closed after a failed open",
            committed=None,
        )
    try:
        closer(opened_name)
    except Exception as exc:
        return make_open_document_uncertain(
            "OPEN_DOCUMENT_ROLLBACK_UNCERTAIN",
            str(exc) or type(exc).__name__,
            committed=None,
        )
    if lookup_document(app, opened_name) is not None:
        return make_open_document_uncertain(
            "OPEN_DOCUMENT_ROLLBACK_UNCERTAIN",
            f"Document {opened_name!r} could not be closed after a failed open",
            committed=None,
        )
    return make_open_document_compensated(
        "OPEN_DOCUMENT_FAILED",
        f"Open for {opened_name!r} failed and was rolled back",
    )


def run_open_document(
    collaborators: OpenDocumentCollaborators,
    path: object,
    module: str | None = None,
) -> OpenDocumentResult:
    if module is not None and (not isinstance(module, str) or not module.strip()):
        return _failure(OpenDocumentError("INVALID_ARGUMENT", "module must be a nonempty string"))
    request = build_open_document_request(path)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(OpenDocumentError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    prep = prepare_open_document(app, request)
    if prep is not None:
        return prep
    perf, opened_name = perform_open_document(app, request, module)
    if perf is not None or opened_name is None:
        return perf if perf is not None else _failure(OpenDocumentError("OPEN_DOCUMENT_FAILED", "Open failed"))
    verified = verify_open_document(app, request, opened_name)
    if verified is not None:
        return verified
    return compensate_open_document(app, opened_name)


class _OpenDocumentRpcFacade(Protocol):
    _cad_collaborators: OpenDocumentCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...
    def _dispatch_snapshot_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_open_document(self: _OpenDocumentRpcFacade, path: str, module: str | None = None) -> dict[str, object]:
    collaborators = self._cad_collaborators
    dispatch = self._dispatch_gui if os.path.splitext(path)[1].lower() == ".fcstd" else self._dispatch_snapshot_gui
    res = dispatch(lambda: run_open_document(collaborators, path, module))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("open_document", rpc_open_document)


__all__ = [
    "OpenDocumentCollaborators",
    "OpenDocumentError",
    "build_open_document_request",
    "rpc_open_document",
    "run_open_document",
    "TYPED_RPC_HANDLER",
]
