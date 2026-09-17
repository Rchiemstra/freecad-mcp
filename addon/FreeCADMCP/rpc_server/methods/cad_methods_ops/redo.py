"""Typed ``redo`` history handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from ...._shared.protocol.redo_contract import (
    DocumentName,
    RedoCollaborators,
    RedoFailure,
    RedoRequest,
    RedoResult,
    make_redo_failure,
    make_redo_success,
    make_redo_uncertain,
)
from .history_runtime import (
    admit_history_document,
    perform_history_action,
    verify_history_stack,
)
from .policy_runtime import app_from
from .typed_rpc_document import document_name


class RedoError(RuntimeError):
    def __init__(self, code: str, message: str, diagnostics: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.diagnostics = diagnostics


def _failure(error: RedoError, *, retry_safe: bool = True) -> RedoFailure:
    return make_redo_failure(
        error.code, str(error), retry_safe=retry_safe, diagnostics=error.diagnostics
    )


def build_redo_request(doc_name: object) -> RedoRequest | RedoFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(RedoError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    return RedoRequest(doc_name=DocumentName(doc_name))


def run_redo(
    collaborators: RedoCollaborators,
    doc_name: object,
) -> RedoResult:
    request = build_redo_request(doc_name)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(RedoError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = admit_history_document(app, str(request.doc_name))
    if document is None:
        return _failure(RedoError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}"))
    stack_issue = verify_history_stack(document, action_name="redo", count_attr="RedoCount")
    if stack_issue == "INVALID_DOCUMENT":
        return _failure(RedoError("INVALID_DOCUMENT", "document cannot redo"))
    if stack_issue == "EMPTY_HISTORY_STACK":
        return _failure(RedoError("EMPTY_HISTORY_STACK", "Nothing to redo"), retry_safe=True)
    try:
        perform_history_action(document, "redo")
    except Exception as exc:
        return make_redo_uncertain(
            "REDO_FAILED",
            str(exc) or type(exc).__name__,
            committed=None,
        )
    if admit_history_document(app, str(request.doc_name)) is None:
        return make_redo_uncertain(
            "REDO_FAILED",
            f"Document {request.doc_name!r} is not open after redo",
            committed=None,
        )
    if document_name(document) != str(request.doc_name):
        return make_redo_uncertain(
            "DOCUMENT_IDENTITY_MISMATCH",
            "Document identity changed during redo",
            committed=None,
        )
    return make_redo_success(DocumentName(str(request.doc_name)))


class _RedoRpcFacade(Protocol):
    _cad_collaborators: RedoCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_redo(
    self: _RedoRpcFacade,
    doc_name: object,
    operation_id: object = None,
    expected_redo_count: object = None,
    expected_redo_head: object = None,
) -> dict[str, object]:
    if operation_id is not None or not isinstance(doc_name, str):
        # Lazy native history-head redo. Keep this out of the typed mypy graph:
        # follow_imports=normal on cad_methods_ops would otherwise typecheck the
        # untyped recompute_helpers -> cad_mutation -> mutation_readiness chain.
        if TYPE_CHECKING:
            def history_redo(
                rpc: object,
                doc_selector: object,
                operation_id: object = None,
                expected_redo_count: object = None,
                expected_redo_head: object = None,
            ) -> dict[str, object]: ...
        else:
            from .recompute_helpers import redo as history_redo

        return history_redo(
            self,
            doc_name,
            operation_id,
            expected_redo_count,
            expected_redo_head,
        )
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_redo(collaborators, doc_name))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("redo", rpc_redo)


__all__ = [
    "RedoCollaborators",
    "RedoError",
    "build_redo_request",
    "rpc_redo",
    "run_redo",
    "TYPED_RPC_HANDLER",
]
