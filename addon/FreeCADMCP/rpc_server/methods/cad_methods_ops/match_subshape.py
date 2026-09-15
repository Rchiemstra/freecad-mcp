"""Typed ``match_subshape`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ...._shared.protocol.match_subshape_contract import (
    MatchSubshapeCollaborators,
    MatchSubshapeFailure,
    MatchSubshapeRequest,
    MatchSubshapeResult,
    DocumentName,
    ObjectName,
    make_match_subshape_failure,
    make_match_subshape_success,
)
from . import diagnostics_io_actions
from .policy_runtime import app_from, lookup_document, lookup_object, optional_recompute
from .typed_runtime import as_float, as_str


class MatchSubshapeError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: MatchSubshapeError, *, retry_safe: bool = True) -> MatchSubshapeFailure:
    return make_match_subshape_failure(error.code, str(error), retry_safe=retry_safe)


def build_match_subshape_request(
    doc_name: object, source_object: object, source_subshape: object, target_object: object, limit: object, tolerance: object,
) -> MatchSubshapeRequest | MatchSubshapeFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(MatchSubshapeError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(source_object, str) or not source_object.strip():
        return _failure(MatchSubshapeError("INVALID_ARGUMENT", "source_object must be a nonempty string"))
    if not isinstance(source_subshape, str) or not source_subshape.strip():
        return _failure(MatchSubshapeError("INVALID_ARGUMENT", "source_subshape must be a nonempty string"))
    if not isinstance(target_object, str) or not target_object.strip():
        return _failure(MatchSubshapeError("INVALID_ARGUMENT", "target_object must be a nonempty string"))
    if not isinstance(limit, (int, float)) or isinstance(limit, bool):
        return _failure(MatchSubshapeError("INVALID_ARGUMENT", "limit must be numeric"))
    if not isinstance(tolerance, (int, float)) or isinstance(tolerance, bool):
        return _failure(MatchSubshapeError("INVALID_ARGUMENT", "tolerance must be numeric"))
    return MatchSubshapeRequest(doc_name=DocumentName(doc_name), source_object=ObjectName(source_object), source_subshape=source_subshape, target_object=ObjectName(target_object), limit=int(limit), tolerance=float(tolerance))


def run_match_subshape(
    collaborators: MatchSubshapeCollaborators,
    doc_name: object, source_object: object, source_subshape: object, target_object: object, limit: object, tolerance: object,
) -> MatchSubshapeResult:
    request = build_match_subshape_request(doc_name, source_object, source_subshape, target_object, limit, tolerance)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(MatchSubshapeError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(MatchSubshapeError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}"))
    if lookup_object(document, str(request.source_object)) is None or lookup_object(document, str(request.target_object)) is None:
        return _failure(MatchSubshapeError("OBJECT_NOT_FOUND", "Object not found"))
    optional_recompute(collaborators, document)
    try:
        payload = diagnostics_io_actions.match_subshape(document, str(request.source_object), str(request.source_subshape), str(request.target_object), int(request.limit), float(request.tolerance))
    except Exception as exc:
        return _failure(MatchSubshapeError("MATCH_SUBSHAPE_FAILED", str(exc) or type(exc).__name__))
    return make_match_subshape_success(
        source=as_str(payload["source"]),
        target=as_str(payload["target"]),
        matches=payload["matches"]
    )


class _MatchSubshapeRpcFacade(Protocol):
    _cad_collaborators: MatchSubshapeCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_match_subshape(
    self: _MatchSubshapeRpcFacade,
    doc_name: str, source_object: str, source_subshape: str, target_object: str, limit: int, tolerance: float,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_match_subshape(collaborators, doc_name, source_object, source_subshape, target_object, limit, tolerance))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("match_subshape", rpc_match_subshape)


__all__ = [
    "MatchSubshapeCollaborators",
    "MatchSubshapeError",
    "build_match_subshape_request",
    "rpc_match_subshape",
    "run_match_subshape",
    "TYPED_RPC_HANDLER",
]
