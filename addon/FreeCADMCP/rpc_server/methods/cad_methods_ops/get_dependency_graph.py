"""Typed ``get_dependency_graph`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ...._shared.protocol.get_dependency_graph_contract import (
    GetDependencyGraphCollaborators,
    GetDependencyGraphFailure,
    GetDependencyGraphRequest,
    GetDependencyGraphResult,
    DocumentName,
    ObjectName,
    make_get_dependency_graph_failure,
    make_get_dependency_graph_success,
)
from . import diagnostics_io_actions
from .policy_runtime import app_from, lookup_document, lookup_object, optional_recompute
from .typed_runtime import as_float, as_int, as_str


class GetDependencyGraphError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: GetDependencyGraphError, *, retry_safe: bool = True) -> GetDependencyGraphFailure:
    return make_get_dependency_graph_failure(error.code, str(error), retry_safe=retry_safe)


def build_get_dependency_graph_request(
    doc_name: object, root: object,
) -> GetDependencyGraphRequest | GetDependencyGraphFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(GetDependencyGraphError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(root, str) or not root.strip():
        return _failure(GetDependencyGraphError("INVALID_ARGUMENT", "root must be a nonempty string"))
    return GetDependencyGraphRequest(doc_name=DocumentName(doc_name), root=ObjectName(root))


def run_get_dependency_graph(
    collaborators: GetDependencyGraphCollaborators,
    doc_name: object, root: object,
) -> GetDependencyGraphResult:
    request = build_get_dependency_graph_request(doc_name, root)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(GetDependencyGraphError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(GetDependencyGraphError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}"))
    if lookup_object(document, str(request.root)) is None:
        return _failure(GetDependencyGraphError("OBJECT_NOT_FOUND", "Object not found"))
    optional_recompute(collaborators, document)
    try:
        payload = diagnostics_io_actions.get_dependency_graph(document, str(request.root))
    except Exception as exc:
        return _failure(GetDependencyGraphError("GET_DEPENDENCY_GRAPH_FAILED", str(exc) or type(exc).__name__))
    return make_get_dependency_graph_success(
        root=as_str(payload["root"]),
        history_order=payload["history_order"],
        edges=payload["edges"],
        cycle_detected=bool(payload["cycle_detected"]),
        node_count=as_int(payload["node_count"])
    )


class _GetDependencyGraphRpcFacade(Protocol):
    _cad_collaborators: GetDependencyGraphCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_get_dependency_graph(
    self: _GetDependencyGraphRpcFacade,
    doc_name: str, root: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_get_dependency_graph(collaborators, doc_name, root))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("get_dependency_graph", rpc_get_dependency_graph)


__all__ = [
    "GetDependencyGraphCollaborators",
    "GetDependencyGraphError",
    "build_get_dependency_graph_request",
    "rpc_get_dependency_graph",
    "run_get_dependency_graph",
    "TYPED_RPC_HANDLER",
]
