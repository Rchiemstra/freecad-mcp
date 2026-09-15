"""Typed ``list_expressions`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from . import diagnostics_io_actions
from .policy_runtime import app_from, lookup_document, lookup_object, optional_recompute
from .typed_runtime import as_str


class ListExpressionsError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(code: str, message: str) -> dict[str, object]:
    return {
        "success": False,
        "ok": False,
        "outcome": "rejected",
        "error_code": code,
        "error": message,
        "retry_safe": True,
    }


def run_list_expressions(collaborators: object, doc_name: str, object_name: str) -> dict[str, object]:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure("INVALID_ARGUMENT", "doc_name must be a nonempty string")
    if not isinstance(object_name, str) or not object_name.strip():
        return _failure("INVALID_ARGUMENT", "object_name must be a nonempty string")
    app = app_from(collaborators)
    if app is None:
        return _failure("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing")
    document = lookup_document(app, doc_name)
    if document is None:
        return _failure("DOCUMENT_NOT_FOUND", f"Document not found: {doc_name!r}")
    if lookup_object(document, object_name) is None:
        return _failure("OBJECT_NOT_FOUND", "Object not found")
    optional_recompute(collaborators, document)
    try:
        payload = diagnostics_io_actions.list_expressions(document, object_name)
    except Exception as exc:
        return _failure("LIST_EXPRESSIONS_FAILED", str(exc) or type(exc).__name__)
    return {
        "success": True,
        "ok": True,
        "outcome": "observed",
        "retry_safe": False,
        "object": as_str(payload["object"]),
        "expressions": payload["expressions"],
        "count": int(payload["count"]),
    }


class _ListExpressionsRpcFacade(Protocol):
    _cad_collaborators: object

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_list_expressions(
    self: _ListExpressionsRpcFacade,
    doc_name: str,
    object_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_list_expressions(collaborators, doc_name, object_name))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("list_expressions", rpc_list_expressions)


__all__ = ["rpc_list_expressions", "run_list_expressions", "TYPED_RPC_HANDLER"]
