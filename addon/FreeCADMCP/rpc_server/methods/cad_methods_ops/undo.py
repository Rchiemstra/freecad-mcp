"""Typed ``undo`` history handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from ...._shared.protocol.undo_contract import (
    DocumentName,
    UndoCollaborators,
    UndoFailure,
    UndoRequest,
    UndoResult,
    make_undo_failure,
    make_undo_success,
    make_undo_uncertain,
)
from .history_runtime import (
    admit_history_document,
    perform_history_action,
    verify_history_stack,
)
from .policy_runtime import app_from
from .typed_rpc_document import document_name


class UndoError(RuntimeError):
    def __init__(self, code: str, message: str, diagnostics: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.diagnostics = diagnostics


def _failure(error: UndoError, *, retry_safe: bool = True) -> UndoFailure:
    return make_undo_failure(
        error.code, str(error), retry_safe=retry_safe, diagnostics=error.diagnostics
    )


def build_undo_request(doc_name: object) -> UndoRequest | UndoFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(UndoError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    return UndoRequest(doc_name=DocumentName(doc_name))


def run_undo(
    collaborators: UndoCollaborators,
    doc_name: object,
) -> UndoResult:
    request = build_undo_request(doc_name)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(UndoError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = admit_history_document(app, str(request.doc_name))
    if document is None:
        return _failure(UndoError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}"))
    stack_issue = verify_history_stack(document, action_name="undo", count_attr="UndoCount")
    if stack_issue == "INVALID_DOCUMENT":
        return _failure(UndoError("INVALID_DOCUMENT", "document cannot undo"))
    if stack_issue == "EMPTY_HISTORY_STACK":
        return _failure(UndoError("EMPTY_HISTORY_STACK", "Nothing to undo"), retry_safe=True)
    try:
        perform_history_action(document, "undo")
    except Exception as exc:
        return make_undo_uncertain(
            "UNDO_FAILED",
            str(exc) or type(exc).__name__,
            committed=None,
        )
    if admit_history_document(app, str(request.doc_name)) is None:
        return make_undo_uncertain(
            "UNDO_FAILED",
            f"Document {request.doc_name!r} is not open after undo",
            committed=None,
        )
    if document_name(document) != str(request.doc_name):
        return make_undo_uncertain(
            "DOCUMENT_IDENTITY_MISMATCH",
            "Document identity changed during undo",
            committed=None,
        )
    return make_undo_success(DocumentName(str(request.doc_name)))


class _UndoRpcFacade(Protocol):
    _cad_collaborators: UndoCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_undo(
    self: _UndoRpcFacade,
    doc_name: object,
    operation_id: object = None,
    expected_undo_count: object = None,
    expected_undo_head: object = None,
) -> dict[str, object]:
    if operation_id is not None or not isinstance(doc_name, str):
        # Lazy native history-head undo. Keep this out of the typed mypy graph:
        # follow_imports=normal on cad_methods_ops would otherwise typecheck the
        # untyped recompute_helpers -> cad_mutation -> mutation_readiness chain.
        if TYPE_CHECKING:
            def history_undo(
                rpc: object,
                doc_selector: object,
                operation_id: object = None,
                expected_undo_count: object = None,
                expected_undo_head: object = None,
            ) -> dict[str, object]: ...
        else:
            from .recompute_helpers import undo as history_undo

        return history_undo(
            self,
            doc_name,
            operation_id,
            expected_undo_count,
            expected_undo_head,
        )
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_undo(collaborators, doc_name))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("undo", rpc_undo)


__all__ = [
    "UndoCollaborators",
    "UndoError",
    "build_undo_request",
    "rpc_undo",
    "run_undo",
    "TYPED_RPC_HANDLER",
]
