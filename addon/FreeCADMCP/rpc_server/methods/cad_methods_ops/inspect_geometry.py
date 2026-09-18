"""Typed ``inspect_geometry`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

try:
    from ...._shared.protocol.inspect_geometry_contract import (
        InspectGeometryCollaborators,
        InspectGeometryFailure,
        InspectGeometryRequest,
        InspectGeometryResult,
        DocumentName,
        ObjectName,
        make_inspect_geometry_failure,
        make_inspect_geometry_success,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.inspect_geometry_contract import (
        InspectGeometryCollaborators,
        InspectGeometryFailure,
        InspectGeometryRequest,
        InspectGeometryResult,
        DocumentName,
        ObjectName,
        make_inspect_geometry_failure,
        make_inspect_geometry_success,
    )
from . import diagnostics_shape_actions
from .policy_runtime import app_from, lookup_document, lookup_object, optional_recompute
from .typed_runtime import as_float, as_str


class InspectGeometryError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: InspectGeometryError, *, retry_safe: bool = True) -> InspectGeometryFailure:
    return make_inspect_geometry_failure(error.code, str(error), retry_safe=retry_safe)


def build_inspect_geometry_request(
    doc_name: object, object_name: object, subshape: object,
) -> InspectGeometryRequest | InspectGeometryFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(InspectGeometryError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(object_name, str) or not object_name.strip():
        return _failure(InspectGeometryError("INVALID_ARGUMENT", "object_name must be a nonempty string"))
    if subshape is not None and not isinstance(subshape, str):
        return _failure(InspectGeometryError("INVALID_ARGUMENT", "subshape must be a string when provided"))
    return InspectGeometryRequest(doc_name=DocumentName(doc_name), object_name=ObjectName(object_name), subshape=subshape)


def run_inspect_geometry(
    collaborators: InspectGeometryCollaborators,
    doc_name: object, object_name: object, subshape: object,
) -> InspectGeometryResult:
    request = build_inspect_geometry_request(doc_name, object_name, subshape)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(InspectGeometryError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(InspectGeometryError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}"))
    if lookup_object(document, str(request.object_name)) is None:
        return _failure(InspectGeometryError("OBJECT_NOT_FOUND", "Object not found"))
    optional_recompute(collaborators, document)
    subshape = request.subshape if isinstance(request.subshape, str) and request.subshape else None
    try:
        payload = diagnostics_shape_actions.inspect_geometry(
            document,
            str(request.object_name),
            subshape,
        )
    except Exception as exc:
        return _failure(InspectGeometryError("INSPECT_GEOMETRY_FAILED", str(exc) or type(exc).__name__))
    placement = payload.get("placement")
    global_placement = payload.get("global_placement")
    parent_chain = payload.get("parent_chain")
    local_bbox = payload.get("local_bbox")
    global_bbox = payload.get("global_bbox")
    return make_inspect_geometry_success(
        object=as_str(payload["object"]),
        type_id=as_str(payload["type_id"]),
        placement=placement if isinstance(placement, dict) else {},
        global_placement=global_placement if isinstance(global_placement, dict) else {},
        parent_chain=parent_chain if isinstance(parent_chain, list) else [],
        local_bbox=local_bbox if isinstance(local_bbox, dict) else {},
        global_bbox=global_bbox if isinstance(global_bbox, dict) else {},
    )


class _InspectGeometryRpcFacade(Protocol):
    _cad_collaborators: InspectGeometryCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_inspect_geometry(
    self: _InspectGeometryRpcFacade,
    doc_name: str, object_name: str, subshape: str | None,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_inspect_geometry(collaborators, doc_name, object_name, subshape))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("inspect_geometry", rpc_inspect_geometry)


__all__ = [
    "InspectGeometryCollaborators",
    "InspectGeometryError",
    "build_inspect_geometry_request",
    "rpc_inspect_geometry",
    "run_inspect_geometry",
    "TYPED_RPC_HANDLER",
]
