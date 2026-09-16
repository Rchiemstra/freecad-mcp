"""Typed ``snapshot`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ...._shared.protocol.snapshot_contract import (
    DocumentName,
    SnapshotCollaborators,
    SnapshotFailure,
    SnapshotRequest,
    SnapshotResult,
    make_snapshot_failure,
    make_snapshot_success,
)
from . import diagnostics_io_actions
from .policy_runtime import app_from, lookup_document, optional_recompute
from .typed_runtime import as_int


class SnapshotError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: SnapshotError, *, retry_safe: bool = True) -> SnapshotFailure:
    return make_snapshot_failure(error.code, str(error), retry_safe=retry_safe)


def build_snapshot_request(doc_name: object) -> SnapshotRequest | SnapshotFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(SnapshotError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    return SnapshotRequest(doc_name=DocumentName(doc_name))


def run_snapshot(collaborators: SnapshotCollaborators, doc_name: str) -> SnapshotResult:
    request = build_snapshot_request(doc_name)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(SnapshotError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(SnapshotError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}"))
    optional_recompute(collaborators, document)
    try:
        payload = diagnostics_io_actions.snapshot_document(document)
    except Exception as exc:
        return _failure(SnapshotError("SNAPSHOT_FAILED", str(exc) or type(exc).__name__))
    return make_snapshot_success(
        str(payload["snapshot_id"]),
        str(payload["doc"]),
        as_int(payload["count"]),
    )


class _SnapshotRpcFacade(Protocol):
    _cad_collaborators: SnapshotCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_snapshot(self: _SnapshotRpcFacade, doc_name: str) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_snapshot(collaborators, doc_name))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("snapshot", rpc_snapshot)


__all__ = [
    "SnapshotCollaborators",
    "SnapshotError",
    "build_snapshot_request",
    "rpc_snapshot",
    "run_snapshot",
    "TYPED_RPC_HANDLER",
]
