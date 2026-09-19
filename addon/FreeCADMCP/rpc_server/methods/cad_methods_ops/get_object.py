"""Typed ``get_object`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

try:
    from ...._shared.protocol.get_object_contract import (
        DocumentName,
        GetObjectCollaborators,
        GetObjectFailure,
        GetObjectRequest,
        GetObjectResult,
        ObjectName,
        make_get_object_failure,
        make_get_object_success,
        parse_get_object_response,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.get_object_contract import (
        DocumentName,
        GetObjectCollaborators,
        GetObjectFailure,
        GetObjectRequest,
        GetObjectResult,
        ObjectName,
        make_get_object_failure,
        make_get_object_success,
        parse_get_object_response,
    )
from .policy_runtime import app_from, lookup_document, lookup_object


class GetObjectError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: GetObjectError, *, retry_safe: bool = True) -> GetObjectFailure:
    return make_get_object_failure(error.code, str(error), retry_safe=retry_safe)


def build_get_object_request(
    doc_name: object,
    obj_name: object,
) -> GetObjectRequest | GetObjectFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(GetObjectError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(obj_name, str) or not obj_name.strip():
        return _failure(GetObjectError("INVALID_ARGUMENT", "obj_name must be a nonempty string"))
    return GetObjectRequest(doc_name=DocumentName(doc_name), obj_name=ObjectName(obj_name))


def _normalize_dispatch_result(raw: object) -> GetObjectResult:
    if isinstance(raw, dict):
        return parse_get_object_response(raw)
    return parse_get_object_response(raw)


def run_get_object(
    collaborators: GetObjectCollaborators,
    doc_name: object,
    obj_name: object,
) -> GetObjectResult:
    request = build_get_object_request(doc_name, obj_name)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(GetObjectError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None or not document:
        return _failure(
            GetObjectError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}")
        )
    obj = lookup_object(document, str(request.obj_name))
    if obj is None:
        return _failure(GetObjectError("OBJECT_NOT_FOUND", "Object not found"))
    serialize = getattr(collaborators, "serialize_object", None)
    if not callable(serialize):
        return _failure(
            GetObjectError("MISSING_DEPENDENCY", "serialize_object collaborator is unavailable"),
            retry_safe=False,
        )
    try:
        payload = serialize(obj)
    except Exception as exc:
        return _failure(
            GetObjectError(
                "GET_OBJECT_SERIALIZE_FAILED",
                str(exc) or type(exc).__name__,
            ),
            retry_safe=False,
        )
    if not isinstance(payload, dict):
        return _failure(
            GetObjectError(
                "GET_OBJECT_SERIALIZE_FAILED",
                "serialize_object must return a mapping",
            ),
            retry_safe=False,
        )
    object_name = str(getattr(obj, "Name", request.obj_name))
    return make_get_object_success(object_name, payload)


class _GetObjectRpcFacade(Protocol):
    _cad_collaborators: GetObjectCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_get_object(
    self: _GetObjectRpcFacade,
    doc_name: str,
    obj_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_get_object(collaborators, doc_name, obj_name))
    normalized = _normalize_dispatch_result(res)
    return dict(normalized)


TYPED_RPC_HANDLER = ("get_object", rpc_get_object)


__all__ = [
    "TYPED_RPC_HANDLER",
    "GetObjectCollaborators",
    "GetObjectError",
    "build_get_object_request",
    "rpc_get_object",
    "run_get_object",
]
