"""Typed ``get_sketch_diagnostics`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from . import diagnostics_io_actions
from .policy_runtime import app_from, lookup_document, lookup_object, optional_recompute
from .typed_runtime import as_str


def _failure(code: str, message: str) -> dict[str, object]:
    return {
        "success": False,
        "ok": False,
        "outcome": "rejected",
        "error_code": code,
        "error": message,
        "retry_safe": True,
    }


def run_get_sketch_diagnostics(
    collaborators: object, doc_name: str, sketch_name: str
) -> dict[str, object]:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure("INVALID_ARGUMENT", "doc_name must be a nonempty string")
    if not isinstance(sketch_name, str) or not sketch_name.strip():
        return _failure("INVALID_ARGUMENT", "sketch_name must be a nonempty string")
    app = app_from(collaborators)
    if app is None:
        return _failure("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing")
    document = lookup_document(app, doc_name)
    if document is None:
        return _failure("DOCUMENT_NOT_FOUND", f"Document not found: {doc_name!r}")
    if lookup_object(document, sketch_name) is None:
        return _failure("OBJECT_NOT_FOUND", "Sketch not found")
    optional_recompute(collaborators, document)
    try:
        payload = diagnostics_io_actions.get_sketch_diagnostics(document, sketch_name)
    except Exception as exc:
        return _failure("GET_SKETCH_DIAGNOSTICS_FAILED", str(exc) or type(exc).__name__)
    return {
        "success": True,
        "ok": True,
        "outcome": "observed",
        "retry_safe": False,
        "sketch_name": as_str(payload["sketch_name"]),
        "geometry_count": int(payload["geometry_count"]),
        "constraint_count": int(payload["constraint_count"]),
        "conflict": bool(payload["conflict"]),
    }


class _GetSketchDiagnosticsRpcFacade(Protocol):
    _cad_collaborators: object

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_get_sketch_diagnostics(
    self: _GetSketchDiagnosticsRpcFacade, doc_name: str, sketch_name: str
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_get_sketch_diagnostics(collaborators, doc_name, sketch_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("get_sketch_diagnostics", rpc_get_sketch_diagnostics)


__all__ = ["rpc_get_sketch_diagnostics", "run_get_sketch_diagnostics", "TYPED_RPC_HANDLER"]
