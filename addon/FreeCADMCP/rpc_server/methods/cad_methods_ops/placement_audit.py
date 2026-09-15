"""Typed ``placement_audit`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from . import diagnostics_shape_actions
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


def run_placement_audit(collaborators: object, doc_name: str) -> dict[str, object]:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure("INVALID_ARGUMENT", "doc_name must be a nonempty string")
    app = app_from(collaborators)
    if app is None:
        return _failure("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing")
    document = lookup_document(app, doc_name)
    if document is None:
        return _failure("DOCUMENT_NOT_FOUND", f"Document not found: {doc_name!r}")
    optional_recompute(collaborators, document)
    try:
        payload = diagnostics_shape_actions.placement_audit(document)
    except Exception as exc:
        return _failure("PLACEMENT_AUDIT_FAILED", str(exc) or type(exc).__name__)
    return {"success": True, "ok": True, "outcome": "observed", "retry_safe": False, **payload}


class _RpcFacade(Protocol):
    _cad_collaborators: object

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_placement_audit(self: _RpcFacade, doc_name: str) -> dict[str, object]:
    res = self._dispatch_gui(lambda: run_placement_audit(self._cad_collaborators, doc_name))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("placement_audit", rpc_placement_audit)

__all__ = ["rpc_placement_audit", "run_placement_audit", "TYPED_RPC_HANDLER"]
