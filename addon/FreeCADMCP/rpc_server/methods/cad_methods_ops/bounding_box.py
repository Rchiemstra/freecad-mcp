"""Typed ``bounding_box`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ...._shared.protocol.bounding_box_contract import (
    BoundingBoxCollaborators,
    BoundingBoxFailure,
    BoundingBoxRequest,
    BoundingBoxResult,
    DocumentName,
    ObjectName,
    make_bounding_box_failure,
    make_bounding_box_success,
)
from . import measure_io_actions
from .policy_runtime import app_from, lookup_document, lookup_object, optional_recompute
from .typed_runtime import as_float, as_str


class BoundingBoxError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: BoundingBoxError, *, retry_safe: bool = True) -> BoundingBoxFailure:
    return make_bounding_box_failure(error.code, str(error), retry_safe=retry_safe)


def build_bounding_box_request(
    doc_name: object, obj_name: object
) -> BoundingBoxRequest | BoundingBoxFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(BoundingBoxError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(obj_name, str) or not obj_name.strip():
        return _failure(BoundingBoxError("INVALID_ARGUMENT", "obj_name must be a nonempty string"))
    return BoundingBoxRequest(doc_name=DocumentName(doc_name), obj_name=ObjectName(obj_name))


def run_bounding_box(
    collaborators: BoundingBoxCollaborators,
    doc_name: str,
    obj_name: str,
) -> BoundingBoxResult:
    request = build_bounding_box_request(doc_name, obj_name)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(BoundingBoxError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(BoundingBoxError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}"))
    if lookup_object(document, str(request.obj_name)) is None:
        return _failure(BoundingBoxError("OBJECT_NOT_FOUND", "Object not found"))
    optional_recompute(collaborators, document)
    try:
        payload = measure_io_actions.bounding_box(document, str(request.obj_name))
    except Exception as exc:
        return _failure(BoundingBoxError("BOUNDING_BOX_FAILED", str(exc) or type(exc).__name__))
    return make_bounding_box_success(
        object=as_str(payload["object"]),
        xmin=as_float(payload["xmin"]),
        ymin=as_float(payload["ymin"]),
        zmin=as_float(payload["zmin"]),
        xmax=as_float(payload["xmax"]),
        ymax=as_float(payload["ymax"]),
        zmax=as_float(payload["zmax"]),
        dx=as_float(payload["dx"]),
        dy=as_float(payload["dy"]),
        dz=as_float(payload["dz"]),
        diagonal=as_float(payload["diagonal"]),
        frame=as_str(payload["frame"]),
    )


class _BoundingBoxRpcFacade(Protocol):
    _cad_collaborators: BoundingBoxCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_bounding_box(
    self: _BoundingBoxRpcFacade,
    doc_name: str,
    obj_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_bounding_box(collaborators, doc_name, obj_name))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("bounding_box", rpc_bounding_box)


__all__ = [
    "BoundingBoxCollaborators",
    "BoundingBoxError",
    "build_bounding_box_request",
    "rpc_bounding_box",
    "run_bounding_box",
    "TYPED_RPC_HANDLER",
]
