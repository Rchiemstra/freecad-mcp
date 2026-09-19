"""Typed ``validate_geometry`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

try:
    from ...._shared.protocol.validate_geometry_contract import (
        ValidateGeometryCollaborators,
        ValidateGeometryFailure,
        ValidateGeometryRequest,
        ValidateGeometryResult,
        DocumentName,
        ObjectName,
        make_validate_geometry_failure,
        make_validate_geometry_success,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.validate_geometry_contract import (
        ValidateGeometryCollaborators,
        ValidateGeometryFailure,
        ValidateGeometryRequest,
        ValidateGeometryResult,
        DocumentName,
        ObjectName,
        make_validate_geometry_failure,
        make_validate_geometry_success,
    )
from . import measure_io_actions
from .policy_runtime import app_from, lookup_document, lookup_object, optional_recompute
from .typed_runtime import as_float, as_int, as_str


class ValidateGeometryError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: ValidateGeometryError, *, retry_safe: bool = True) -> ValidateGeometryFailure:
    return make_validate_geometry_failure(error.code, str(error), retry_safe=retry_safe)


def build_validate_geometry_request(
    doc_name: object, obj_name: object,
) -> ValidateGeometryRequest | ValidateGeometryFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(ValidateGeometryError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(obj_name, str) or not obj_name.strip():
        return _failure(ValidateGeometryError("INVALID_ARGUMENT", "obj_name must be a nonempty string"))
    return ValidateGeometryRequest(doc_name=DocumentName(doc_name), obj_name=ObjectName(obj_name))


def run_validate_geometry(
    collaborators: ValidateGeometryCollaborators,
    doc_name: object, obj_name: object,
) -> ValidateGeometryResult:
    request = build_validate_geometry_request(doc_name, obj_name)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(ValidateGeometryError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(ValidateGeometryError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}"))
    if lookup_object(document, str(request.obj_name)) is None:
        return _failure(ValidateGeometryError("OBJECT_NOT_FOUND", "Object not found"))
    optional_recompute(collaborators, document)
    try:
        payload = measure_io_actions.validate_geometry(document, str(request.obj_name))
    except Exception as exc:
        return _failure(ValidateGeometryError("VALIDATE_GEOMETRY_FAILED", str(exc) or type(exc).__name__))
    return make_validate_geometry_success(
        object=as_str(payload["object"]),
        is_null=bool(payload["is_null"]),
        is_valid=bool(payload["is_valid"]),
        is_closed=bool(payload["is_closed"]),
        volume_mm3=as_float(payload["volume_mm3"]),
        area_mm2=as_float(payload["area_mm2"]),
        face_count=as_int(payload["face_count"]),
        edge_count=as_int(payload["edge_count"]),
        vertex_count=as_int(payload["vertex_count"]),
        shape_type=as_str(payload["shape_type"]),
        check_ok=bool(payload["check_ok"]),
        check_errors=payload["check_errors"]
    )


class _ValidateGeometryRpcFacade(Protocol):
    _cad_collaborators: ValidateGeometryCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_validate_geometry(
    self: _ValidateGeometryRpcFacade,
    doc_name: str, obj_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_validate_geometry(collaborators, doc_name, obj_name))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("validate_geometry", rpc_validate_geometry)


__all__ = [
    "ValidateGeometryCollaborators",
    "ValidateGeometryError",
    "build_validate_geometry_request",
    "rpc_validate_geometry",
    "run_validate_geometry",
    "TYPED_RPC_HANDLER",
]
