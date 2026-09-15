"""Typed ``get_global_shape`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ...._shared.protocol.get_global_shape_contract import (
    GetGlobalShapeCollaborators,
    GetGlobalShapeFailure,
    GetGlobalShapeRequest,
    GetGlobalShapeResult,
    DocumentName,
    ObjectName,
    make_get_global_shape_failure,
    make_get_global_shape_success,
)
from . import measure_io_actions
from .policy_runtime import app_from, lookup_document, lookup_object, optional_recompute
from .typed_runtime import as_float, as_int, as_str


class GetGlobalShapeError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: GetGlobalShapeError, *, retry_safe: bool = True) -> GetGlobalShapeFailure:
    return make_get_global_shape_failure(error.code, str(error), retry_safe=retry_safe)


def build_get_global_shape_request(
    doc_name: object, obj_name: object,
) -> GetGlobalShapeRequest | GetGlobalShapeFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(GetGlobalShapeError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(obj_name, str) or not obj_name.strip():
        return _failure(GetGlobalShapeError("INVALID_ARGUMENT", "obj_name must be a nonempty string"))
    return GetGlobalShapeRequest(doc_name=DocumentName(doc_name), obj_name=ObjectName(obj_name))


def run_get_global_shape(
    collaborators: GetGlobalShapeCollaborators,
    doc_name: object, obj_name: object,
) -> GetGlobalShapeResult:
    request = build_get_global_shape_request(doc_name, obj_name)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(GetGlobalShapeError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(GetGlobalShapeError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}"))
    if lookup_object(document, str(request.obj_name)) is None:
        return _failure(GetGlobalShapeError("OBJECT_NOT_FOUND", "Object not found"))
    optional_recompute(collaborators, document)
    try:
        payload = measure_io_actions.get_global_shape(document, str(request.obj_name))
    except Exception as exc:
        return _failure(GetGlobalShapeError("GET_GLOBAL_SHAPE_FAILED", str(exc) or type(exc).__name__))
    return make_get_global_shape_success(
        object=as_str(payload["object"]),
        frame=as_str(payload["frame"]),
        volume_mm3=as_float(payload["volume_mm3"]),
        area_mm2=as_float(payload["area_mm2"]),
        center_of_mass=payload["center_of_mass"],
        bbox=payload["bbox"],
        solids=as_int(payload["solids"]),
        faces=as_int(payload["faces"]),
        edges=as_int(payload["edges"])
    )


class _GetGlobalShapeRpcFacade(Protocol):
    _cad_collaborators: GetGlobalShapeCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_get_global_shape(
    self: _GetGlobalShapeRpcFacade,
    doc_name: str, obj_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_get_global_shape(collaborators, doc_name, obj_name))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("get_global_shape", rpc_get_global_shape)


__all__ = [
    "GetGlobalShapeCollaborators",
    "GetGlobalShapeError",
    "build_get_global_shape_request",
    "rpc_get_global_shape",
    "run_get_global_shape",
    "TYPED_RPC_HANDLER",
]
