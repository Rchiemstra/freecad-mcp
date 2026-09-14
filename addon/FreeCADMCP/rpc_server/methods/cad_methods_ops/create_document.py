"""Typed ``create_document`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.create_document_contract import (
    CreateDocumentCollaborators,
    CreateDocumentFailure,
    CreateDocumentRequest,
    CreateDocumentResult,
    DocumentName,
    make_create_document_failure,
    make_create_document_success,
    make_create_document_uncertain,
)
from .create_document_mutation import CreateDocumentError, run_create_document_native_mutation
from .typed_rpc_document import document_name


@dataclass(frozen=True, slots=True)
class CreateDocumentReceipt:
    """Internal identity captured while applying the mutation."""

    name: str


@dataclass(frozen=True, slots=True)
class CreateDocumentInspection:
    """Read-only data captured after the native-owned recompute."""

    name: DocumentName


def _failure(error: CreateDocumentError, *, retry_safe: bool = True) -> CreateDocumentFailure:
    return make_create_document_failure(
        error.code, str(error), retry_safe=retry_safe, diagnostics=error.diagnostics
    )


def apply_create_document(doc: object, request: CreateDocumentRequest) -> CreateDocumentReceipt:
    """Record the new document identity without recomputing."""

    name = document_name(doc)
    if name != str(request.name) and name:
        return CreateDocumentReceipt(name=name)
    return CreateDocumentReceipt(name=str(request.name))


def read_create_document_result(
    doc: object, receipt: CreateDocumentReceipt
) -> CreateDocumentInspection:
    """Build the public result after the shared mutation recompute."""

    name = document_name(doc)
    if name != receipt.name:
        raise CreateDocumentError(
            "CREATED_DOCUMENT_REPLACED",
            f"Created document name mismatch: {receipt.name!r} vs {name!r}",
        )
    return CreateDocumentInspection(name=DocumentName(name))


def build_create_document_request(
    name: object,
) -> CreateDocumentRequest | CreateDocumentFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(name, str) or not name.strip():
        return _failure(
            CreateDocumentError("INVALID_ARGUMENT", "name must be a nonempty string")
        )
    return CreateDocumentRequest(name=DocumentName(name))


@dataclass(slots=True)
class _CreateDocumentExecution:
    collaborators: CreateDocumentCollaborators
    request: CreateDocumentRequest
    created: CreateDocumentReceipt | None = None
    inspected: CreateDocumentInspection | None = None

    def apply(self, doc: object) -> None:
        self.created = apply_create_document(doc, self.request)

    def inspect(self, doc: object) -> None:
        if self.created is None:
            raise CreateDocumentError(
                "INVALID_CREATE_DOCUMENT_RESULT",
                "Document creation did not return an identity receipt",
            )
        self.inspected = read_create_document_result(doc, self.created)

    def run(self) -> CreateDocumentResult:
        result = run_create_document_native_mutation(
            self.collaborators,
            str(self.request.name),
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_create_document_uncertain(
                "CREATE_DOCUMENT_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected document result",
                committed=True,
            )
        return make_create_document_success(self.inspected.name)


def _app_call(app: object, method: str, *args: object) -> object:
    func = getattr(app, method, None)
    if not callable(func):
        raise CreateDocumentError("FREECAD_UNAVAILABLE", f"FreeCAD is missing {method}")
    return func(*args)


def run_create_document(
    collaborators: CreateDocumentCollaborators,
    name: object,
) -> CreateDocumentResult:
    """Create the document, then seal it through native apply/recompute/inspect."""

    request = build_create_document_request(name)
    if isinstance(request, dict):
        return request
    app = getattr(collaborators, "freecad", None)
    if app is None:
        return _failure(CreateDocumentError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    try:
        existing = _app_call(app, "getDocument", str(request.name))
    except CreateDocumentError as exc:
        return _failure(exc)
    except NameError:
        # FreeCAD.getDocument raises NameError for a missing document.
        existing = None
    if existing is not None:
        return _failure(
            CreateDocumentError(
                "DOCUMENT_ALREADY_EXISTS",
                f"Document already exists: {request.name!r}",
            )
        )
    try:
        created = _app_call(app, "newDocument", str(request.name))
    except Exception as exc:
        wrapped = (
            exc
            if isinstance(exc, CreateDocumentError)
            else CreateDocumentError("CREATE_DOCUMENT_FAILED", str(exc) or type(exc).__name__)
        )
        return _failure(wrapped)
    del created
    result = _CreateDocumentExecution(collaborators, request).run()
    if isinstance(result, dict) and result.get("success") is not True:
        closer = getattr(app, "closeDocument", None)
        if callable(closer):
            try:
                closer(str(request.name))
            except Exception:
                return make_create_document_uncertain(
                    "CREATE_DOCUMENT_ROLLBACK_UNCERTAIN",
                    "Native create_document failed and the new document could not be closed",
                    committed=None,
                    diagnostics={"response": result} if isinstance(result, dict) else None,
                )
    return result


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
    "CreateDocumentInspection",
    "CreateDocumentReceipt",
    "apply_create_document",
    "build_create_document_request",
    "read_create_document_result",
    "rpc_create_document",
    "run_create_document",
    "TYPED_RPC_HANDLER",
]
