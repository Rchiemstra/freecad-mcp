"""Typed ``run_transaction`` mutation handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from . import diagnostics_io_actions
from .policy_runtime import app_from, lookup_document


def _failure(code: str, message: str) -> dict[str, object]:
    return {
        "success": False,
        "ok": False,
        "outcome": "rejected",
        "error_code": code,
        "error": message,
        "retry_safe": True,
    }


def run_run_transaction(
    collaborators: object,
    doc_name: str,
    label: str,
    code: str,
    dry_run: bool = False,
    commit_on_success: bool = True,
) -> dict[str, object]:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure("INVALID_ARGUMENT", "doc_name must be a nonempty string")
    if not isinstance(label, str) or not label.strip():
        return _failure("INVALID_ARGUMENT", "label must be a nonempty string")
    if not isinstance(code, str):
        return _failure("INVALID_ARGUMENT", "code must be a string")
    app = app_from(collaborators)
    if app is None:
        return _failure("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing")
    document = lookup_document(app, doc_name)
    if document is None:
        return _failure("DOCUMENT_NOT_FOUND", f"Document not found: {doc_name!r}")
    try:
        payload = diagnostics_io_actions.run_transaction(
            document, label, code, bool(dry_run), bool(commit_on_success)
        )
    except Exception as exc:
        return _failure("RUN_TRANSACTION_FAILED", str(exc) or type(exc).__name__)
    return {
        "success": True,
        "ok": True,
        "outcome": "committed" if payload.get("committed") else "observed",
        "retry_safe": False,
        **payload,
    }


class _RunTransactionRpcFacade(Protocol):
    _cad_collaborators: object

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_run_transaction(
    self: _RunTransactionRpcFacade,
    doc_name: str,
    label: str,
    code: str,
    dry_run: bool = False,
    commit_on_success: bool = True,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_run_transaction(
            collaborators, doc_name, label, code, dry_run, commit_on_success
        )
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("run_transaction", rpc_run_transaction)


__all__ = ["rpc_run_transaction", "run_run_transaction", "TYPED_RPC_HANDLER"]
