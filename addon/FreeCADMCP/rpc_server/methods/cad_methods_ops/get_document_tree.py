"""Typed ``get_document_tree`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

try:
    from ...._shared.protocol.get_document_tree_contract import (
        DocumentName,
        GetDocumentTreeCollaborators,
        GetDocumentTreeFailure,
        GetDocumentTreeRequest,
        GetDocumentTreeResult,
        make_get_document_tree_failure,
        make_get_document_tree_success,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.get_document_tree_contract import (
        DocumentName,
        GetDocumentTreeCollaborators,
        GetDocumentTreeFailure,
        GetDocumentTreeRequest,
        GetDocumentTreeResult,
        make_get_document_tree_failure,
        make_get_document_tree_success,
    )
from . import assembly_io_actions
from .policy_runtime import app_from, lookup_document, optional_recompute
from .typed_runtime import as_int


class GetDocumentTreeError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: GetDocumentTreeError, *, retry_safe: bool = True) -> GetDocumentTreeFailure:
    return make_get_document_tree_failure(error.code, str(error), retry_safe=retry_safe)


def build_get_document_tree_request(
    doc_name: object,
    root_filter: object,
    max_depth: object,
    include: object,
    include_properties: object,
    selected_nodes: object,
) -> GetDocumentTreeRequest | GetDocumentTreeFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(GetDocumentTreeError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(root_filter, str):
        return _failure(GetDocumentTreeError("INVALID_ARGUMENT", "root_filter must be a string"))
    if type(max_depth) is not int:
        return _failure(GetDocumentTreeError("INVALID_ARGUMENT", "max_depth must be an integer"))
    include_list = None if include is None else list(include) if isinstance(include, list) else None
    if include is not None and include_list is None:
        return _failure(GetDocumentTreeError("INVALID_ARGUMENT", "include must be a list of strings"))
    props_list = None if include_properties is None else list(include_properties) if isinstance(include_properties, list) else None
    if include_properties is not None and props_list is None:
        return _failure(GetDocumentTreeError("INVALID_ARGUMENT", "include_properties must be a list of strings"))
    selected_list = None if selected_nodes is None else list(selected_nodes) if isinstance(selected_nodes, list) else None
    if selected_nodes is not None and selected_list is None:
        return _failure(GetDocumentTreeError("INVALID_ARGUMENT", "selected_nodes must be a list of strings"))
    return GetDocumentTreeRequest(
        doc_name=DocumentName(doc_name),
        root_filter=root_filter,
        max_depth=max_depth,
        include=tuple(include_list) if include_list else None,
        include_properties=tuple(props_list) if props_list else None,
        selected_nodes=tuple(selected_list) if selected_list else None,
    )


def run_get_document_tree(
    collaborators: GetDocumentTreeCollaborators,
    doc_name: str,
    root_filter: str = "",
    max_depth: int = 4,
    include: object = None,
    include_properties: object = None,
    selected_nodes: object = None,
) -> GetDocumentTreeResult:
    request = build_get_document_tree_request(
        doc_name, root_filter, max_depth, include, include_properties, selected_nodes
    )
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(GetDocumentTreeError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(GetDocumentTreeError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}"))
    optional_recompute(collaborators, document)
    try:
        payload = assembly_io_actions.get_document_tree(
            document,
            root_filter=str(request.root_filter),
            max_depth=int(request.max_depth),
            include=list(request.include) if request.include else None,
            include_properties=list(request.include_properties) if request.include_properties else None,
            selected_nodes=list(request.selected_nodes) if request.selected_nodes else None,
        )
    except Exception as exc:
        return _failure(GetDocumentTreeError("GET_DOCUMENT_TREE_FAILED", str(exc) or type(exc).__name__))
    return make_get_document_tree_success(
        doc_name=str(payload["doc_name"]),
        root_filter=str(payload["root_filter"]),
        max_depth=as_int(payload["max_depth"]),
        roots=payload["roots"],
    )


class _GetDocumentTreeRpcFacade(Protocol):
    _cad_collaborators: GetDocumentTreeCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_get_document_tree(
    self: _GetDocumentTreeRpcFacade,
    doc_name: str,
    root_filter: str = "",
    max_depth: int = 4,
    include: object = None,
    include_properties: object = None,
    selected_nodes: object = None,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_get_document_tree(
            collaborators, doc_name, root_filter, max_depth, include, include_properties, selected_nodes
        )
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("get_document_tree", rpc_get_document_tree)


__all__ = [
    "GetDocumentTreeCollaborators",
    "GetDocumentTreeError",
    "build_get_document_tree_request",
    "rpc_get_document_tree",
    "run_get_document_tree",
    "TYPED_RPC_HANDLER",
]
