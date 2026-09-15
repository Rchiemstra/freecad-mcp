"""Typed ``face_normal`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ...._shared.protocol.face_normal_contract import (
    FaceNormalCollaborators,
    FaceNormalFailure,
    FaceNormalRequest,
    FaceNormalResult,
    DocumentName,
    ObjectName,
    make_face_normal_failure,
    make_face_normal_success,
)
from . import diagnostics_shape_actions
from .policy_runtime import app_from, lookup_document, lookup_object, optional_recompute
from .typed_runtime import as_float, as_str


class FaceNormalError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: FaceNormalError, *, retry_safe: bool = True) -> FaceNormalFailure:
    return make_face_normal_failure(error.code, str(error), retry_safe=retry_safe)


def build_face_normal_request(
    doc_name: object, object_name: object, face: object,
) -> FaceNormalRequest | FaceNormalFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(FaceNormalError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(object_name, str) or not object_name.strip():
        return _failure(FaceNormalError("INVALID_ARGUMENT", "object_name must be a nonempty string"))
    if not isinstance(face, str) or not face.strip():
        return _failure(FaceNormalError("INVALID_ARGUMENT", "face must be a nonempty string"))
    return FaceNormalRequest(doc_name=DocumentName(doc_name), object_name=ObjectName(object_name), face=face)


def run_face_normal(
    collaborators: FaceNormalCollaborators,
    doc_name: object, object_name: object, face: object,
) -> FaceNormalResult:
    request = build_face_normal_request(doc_name, object_name, face)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(FaceNormalError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(FaceNormalError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}"))
    if lookup_object(document, str(request.object_name)) is None:
        return _failure(FaceNormalError("OBJECT_NOT_FOUND", "Object not found"))
    optional_recompute(collaborators, document)
    try:
        payload = diagnostics_shape_actions.face_normal(document, str(request.object_name), str(request.face))
    except Exception as exc:
        return _failure(FaceNormalError("FACE_NORMAL_FAILED", str(exc) or type(exc).__name__))
    return make_face_normal_success(
        object=as_str(payload["object"]),
        subshape=as_str(payload["subshape"]),
        shape_type=as_str(payload["type"]),
        global_center=payload["global_center"],
        global_normal=payload["global_normal"]
    )


class _FaceNormalRpcFacade(Protocol):
    _cad_collaborators: FaceNormalCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_face_normal(
    self: _FaceNormalRpcFacade,
    doc_name: str, object_name: str, face: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_face_normal(collaborators, doc_name, object_name, face))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("face_normal", rpc_face_normal)


__all__ = [
    "FaceNormalCollaborators",
    "FaceNormalError",
    "build_face_normal_request",
    "rpc_face_normal",
    "run_face_normal",
    "TYPED_RPC_HANDLER",
]
