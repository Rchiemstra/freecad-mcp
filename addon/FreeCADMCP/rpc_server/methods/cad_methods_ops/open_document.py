"""Typed ``open_document`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.open_document_contract import (
    DocumentName,
    OpenDocumentCollaborators,
    OpenDocumentFailure,
    OpenDocumentRequest,
    OpenDocumentResult,
    PathName,
    make_open_document_failure,
    make_open_document_success,
    make_open_document_uncertain,
)
from .open_document_mutation import OpenDocumentError, run_open_document_native_mutation
from .typed_rpc_document import document_name


@dataclass(frozen=True, slots=True)
class OpenDocumentReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    path: str


@dataclass(frozen=True, slots=True)
class OpenDocumentInspection:
    """Read-only data captured after the native-owned recompute."""

    name: DocumentName
    path: str


def _failure(error: OpenDocumentError, *, retry_safe: bool = True) -> OpenDocumentFailure:
    return make_open_document_failure(
        error.code, str(error), retry_safe=retry_safe, diagnostics=error.diagnostics
    )


def apply_open_document(doc: object, request: OpenDocumentRequest) -> OpenDocumentReceipt:
    """Record the opened document identity without recomputing."""

    return OpenDocumentReceipt(name=document_name(doc), path=str(request.path))


def read_open_document_result(
    doc: object, receipt: OpenDocumentReceipt
) -> OpenDocumentInspection:
    """Build the public result after the shared mutation recompute."""

    return OpenDocumentInspection(name=DocumentName(document_name(doc)), path=receipt.path)


def build_open_document_request(path: object) -> OpenDocumentRequest | OpenDocumentFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(path, str) or not path.strip():
        return _failure(OpenDocumentError("INVALID_ARGUMENT", "path must be a nonempty string"))
    return OpenDocumentRequest(path=PathName(path))


@dataclass(slots=True)
class _OpenDocumentExecution:
    collaborators: OpenDocumentCollaborators
    request: OpenDocumentRequest
    created: OpenDocumentReceipt | None = None
    inspected: OpenDocumentInspection | None = None

    def apply(self, doc: object) -> None:
        self.created = apply_open_document(doc, self.request)

    def inspect(self, doc: object) -> None:
        if self.created is None:
            raise OpenDocumentError(
                "INVALID_OPEN_DOCUMENT_RESULT",
                "Document open did not return an identity receipt",
            )
        self.inspected = read_open_document_result(doc, self.created)

    def run(self, document_name_value: str) -> OpenDocumentResult:
        result = run_open_document_native_mutation(
            self.collaborators,
            document_name_value,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_open_document_uncertain(
                "OPEN_DOCUMENT_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected open_document result",
                committed=True,
            )
        return make_open_document_success(self.inspected.name, self.inspected.path)


def run_open_document(
    collaborators: OpenDocumentCollaborators,
    path: object,
) -> OpenDocumentResult:
    """Open the file, then seal the admitted document through native commit."""

    request = build_open_document_request(path)
    if isinstance(request, dict):
        return request
    app = getattr(collaborators, "freecad", None)
    opener = getattr(app, "openDocument", None)
    if not callable(opener):
        return _failure(OpenDocumentError("FREECAD_UNAVAILABLE", "FreeCAD cannot open documents"))
    try:
        opened = opener(str(request.path))
    except Exception as exc:
        return _failure(OpenDocumentError("OPEN_DOCUMENT_FAILED", str(exc) or type(exc).__name__))
    if opened is None:
        return _failure(
            OpenDocumentError("OPEN_DOCUMENT_FAILED", f"Failed to open: {request.path}")
        )
    opened_name = getattr(opened, "Name", None)
    if not isinstance(opened_name, str) or not opened_name.strip():
        return _failure(OpenDocumentError("OPEN_DOCUMENT_FAILED", "Opened document has no name"))
    result = _OpenDocumentExecution(collaborators, request).run(opened_name)
    if isinstance(result, dict) and result.get("success") is not True:
        closer = getattr(app, "closeDocument", None)
        if callable(closer):
            try:
                closer(opened_name)
            except Exception:
                return make_open_document_uncertain(
                    "OPEN_DOCUMENT_ROLLBACK_UNCERTAIN",
                    "Native open_document failed and the opened document could not be closed",
                    committed=None,
                    diagnostics={"response": result},
                )
    return result


class _OpenDocumentRpcFacade(Protocol):
    _cad_collaborators: OpenDocumentCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_open_document(self: _OpenDocumentRpcFacade, path: str) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_open_document(collaborators, path))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("open_document", rpc_open_document)


__all__ = [
    "OpenDocumentCollaborators",
    "OpenDocumentError",
    "OpenDocumentInspection",
    "OpenDocumentReceipt",
    "apply_open_document",
    "build_open_document_request",
    "read_open_document_result",
    "rpc_open_document",
    "run_open_document",
    "TYPED_RPC_HANDLER",
]
