"""Typed ``diagnose_parametric`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from . import diagnostics_io_actions
from .policy_runtime import app_from, lookup_document, optional_recompute


def _failure(code: str, message: str) -> dict[str, object]:
    return {
        "success": False,
        "ok": False,
        "outcome": "rejected",
        "error_code": code,
        "error": message,
        "retry_safe": True,
    }


def run_diagnose_parametric(
    collaborators: object, doc_name: str, object_name: str | None = None
) -> dict[str, object]:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure("INVALID_ARGUMENT", "doc_name must be a nonempty string")
    if object_name is not None and (not isinstance(object_name, str) or not object_name.strip()):
        return _failure("INVALID_ARGUMENT", "object_name must be a nonempty string when provided")
    app = app_from(collaborators)
    if app is None:
        return _failure("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing")
    document = lookup_document(app, doc_name)
    if document is None:
        return _failure("DOCUMENT_NOT_FOUND", f"Document not found: {doc_name!r}")
    optional_recompute(collaborators, document)
    try:
        payload = diagnostics_io_actions.diagnose_parametric(document, object_name)
    except Exception as exc:
        return _failure("DIAGNOSE_PARAMETRIC_FAILED", str(exc) or type(exc).__name__)
    return {"success": True, "ok": True, "outcome": "observed", "retry_safe": False, **payload}


class _DiagnoseParametricRpcFacade(Protocol):
    _cad_collaborators: object

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_diagnose_parametric(
    self: _DiagnoseParametricRpcFacade, doc_name: str, object_name: str | None = None
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_diagnose_parametric(collaborators, doc_name, object_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("diagnose_parametric", rpc_diagnose_parametric)


__all__ = ["rpc_diagnose_parametric", "run_diagnose_parametric", "TYPED_RPC_HANDLER"]
