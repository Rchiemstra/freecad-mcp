"""Typed ``edge_axis`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

try:
    from ...._shared.protocol.edge_axis_contract import (
        EdgeAxisCollaborators,
        EdgeAxisFailure,
        EdgeAxisRequest,
        EdgeAxisResult,
        DocumentName,
        ObjectName,
        make_edge_axis_failure,
        make_edge_axis_success,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.edge_axis_contract import (
        EdgeAxisCollaborators,
        EdgeAxisFailure,
        EdgeAxisRequest,
        EdgeAxisResult,
        DocumentName,
        ObjectName,
        make_edge_axis_failure,
        make_edge_axis_success,
    )
from . import diagnostics_shape_actions
from .policy_runtime import app_from, lookup_document, lookup_object, optional_recompute
from .typed_runtime import as_float, as_str


class EdgeAxisError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: EdgeAxisError, *, retry_safe: bool = True) -> EdgeAxisFailure:
    return make_edge_axis_failure(error.code, str(error), retry_safe=retry_safe)


def build_edge_axis_request(
    doc_name: object, object_name: object, edge: object,
) -> EdgeAxisRequest | EdgeAxisFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(EdgeAxisError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(object_name, str) or not object_name.strip():
        return _failure(EdgeAxisError("INVALID_ARGUMENT", "object_name must be a nonempty string"))
    if not isinstance(edge, str) or not edge.strip():
        return _failure(EdgeAxisError("INVALID_ARGUMENT", "edge must be a nonempty string"))
    return EdgeAxisRequest(doc_name=DocumentName(doc_name), object_name=ObjectName(object_name), edge=edge)


def run_edge_axis(
    collaborators: EdgeAxisCollaborators,
    doc_name: object, object_name: object, edge: object,
) -> EdgeAxisResult:
    request = build_edge_axis_request(doc_name, object_name, edge)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(EdgeAxisError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(EdgeAxisError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}"))
    if lookup_object(document, str(request.object_name)) is None:
        return _failure(EdgeAxisError("OBJECT_NOT_FOUND", "Object not found"))
    optional_recompute(collaborators, document)
    try:
        payload = diagnostics_shape_actions.edge_axis(document, str(request.object_name), str(request.edge))
    except Exception as exc:
        return _failure(EdgeAxisError("EDGE_AXIS_FAILED", str(exc) or type(exc).__name__))
    return make_edge_axis_success(
        object=as_str(payload["object"]),
        subshape=as_str(payload["subshape"]),
        shape_type=as_str(payload["type"]),
        global_center=payload["global_center"],
        global_normal=payload["global_normal"]
    )


class _EdgeAxisRpcFacade(Protocol):
    _cad_collaborators: EdgeAxisCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_edge_axis(
    self: _EdgeAxisRpcFacade,
    doc_name: str, object_name: str, edge: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_edge_axis(collaborators, doc_name, object_name, edge))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("edge_axis", rpc_edge_axis)


__all__ = [
    "EdgeAxisCollaborators",
    "EdgeAxisError",
    "build_edge_axis_request",
    "rpc_edge_axis",
    "run_edge_axis",
    "TYPED_RPC_HANDLER",
]
