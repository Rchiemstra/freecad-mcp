"""Typed ``audit_hardcoded_dimensions`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ...._shared.protocol.audit_hardcoded_dimensions_contract import (
    AuditHardcodedDimensionsCollaborators,
    AuditHardcodedDimensionsFailure,
    AuditHardcodedDimensionsRequest,
    AuditHardcodedDimensionsResult,
    DocumentName,
    ObjectName,
    make_audit_hardcoded_dimensions_failure,
    make_audit_hardcoded_dimensions_success,
)
from . import diagnostics_shape_actions
from .policy_runtime import app_from, lookup_document, lookup_object, optional_recompute
from .typed_runtime import as_float, as_int, as_str


class AuditHardcodedDimensionsError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: AuditHardcodedDimensionsError, *, retry_safe: bool = True) -> AuditHardcodedDimensionsFailure:
    return make_audit_hardcoded_dimensions_failure(error.code, str(error), retry_safe=retry_safe)


def build_audit_hardcoded_dimensions_request(
    doc_name: object, body_name: object, flag_aliases: object,
) -> AuditHardcodedDimensionsRequest | AuditHardcodedDimensionsFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(AuditHardcodedDimensionsError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(body_name, str) or not body_name.strip():
        return _failure(AuditHardcodedDimensionsError("INVALID_ARGUMENT", "body_name must be a nonempty string"))
    if not isinstance(flag_aliases, bool):
        return _failure(AuditHardcodedDimensionsError("INVALID_ARGUMENT", "flag_aliases must be a boolean"))
    return AuditHardcodedDimensionsRequest(doc_name=DocumentName(doc_name), body_name=ObjectName(body_name), flag_aliases=bool(flag_aliases))


def run_audit_hardcoded_dimensions(
    collaborators: AuditHardcodedDimensionsCollaborators,
    doc_name: object, body_name: object, flag_aliases: object,
) -> AuditHardcodedDimensionsResult:
    request = build_audit_hardcoded_dimensions_request(doc_name, body_name, flag_aliases)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(AuditHardcodedDimensionsError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(AuditHardcodedDimensionsError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}"))
    if lookup_object(document, str(request.body_name)) is None:
        return _failure(AuditHardcodedDimensionsError("OBJECT_NOT_FOUND", "Object not found"))
    optional_recompute(collaborators, document)
    try:
        payload = diagnostics_shape_actions.audit_hardcoded_dimensions(document, str(request.body_name), bool(request.flag_aliases))
    except Exception as exc:
        return _failure(AuditHardcodedDimensionsError("AUDIT_HARDCODED_DIMENSIONS_FAILED", str(exc) or type(exc).__name__))
    return make_audit_hardcoded_dimensions_success(
        clean=bool(payload["ok"]),
        body=as_str(payload["body"]),
        count=as_int(payload["count"]),
        findings=payload["findings"]
    )


class _AuditHardcodedDimensionsRpcFacade(Protocol):
    _cad_collaborators: AuditHardcodedDimensionsCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_audit_hardcoded_dimensions(
    self: _AuditHardcodedDimensionsRpcFacade,
    doc_name: str, body_name: str, flag_aliases: bool,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_audit_hardcoded_dimensions(collaborators, doc_name, body_name, flag_aliases))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("audit_hardcoded_dimensions", rpc_audit_hardcoded_dimensions)


__all__ = [
    "AuditHardcodedDimensionsCollaborators",
    "AuditHardcodedDimensionsError",
    "build_audit_hardcoded_dimensions_request",
    "rpc_audit_hardcoded_dimensions",
    "run_audit_hardcoded_dimensions",
    "TYPED_RPC_HANDLER",
]
