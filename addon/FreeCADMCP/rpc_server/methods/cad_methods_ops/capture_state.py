"""Typed ``capture_state`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ...._shared.protocol.capture_state_contract import (
    CaptureStateCollaborators,
    CaptureStateFailure,
    CaptureStateRequest,
    CaptureStateResult,
    DocumentName,
    make_capture_state_failure,
    make_capture_state_success,
)
from . import diagnostics_io_actions
from .policy_runtime import app_from, lookup_document, optional_recompute


class CaptureStateError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: CaptureStateError, *, retry_safe: bool = True) -> CaptureStateFailure:
    return make_capture_state_failure(error.code, str(error), retry_safe=retry_safe)


def build_capture_state_request(
    doc_name: object, object_names: object
) -> CaptureStateRequest | CaptureStateFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(CaptureStateError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    names = None if object_names is None else list(object_names) if isinstance(object_names, list) else None
    if object_names is not None and names is None:
        return _failure(CaptureStateError("INVALID_ARGUMENT", "object_names must be a list of strings"))
    return CaptureStateRequest(doc_name=DocumentName(doc_name), object_names=names)


def run_capture_state(
    collaborators: CaptureStateCollaborators,
    doc_name: str,
    object_names: object = None,
) -> CaptureStateResult:
    request = build_capture_state_request(doc_name, object_names)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(CaptureStateError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(CaptureStateError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}"))
    optional_recompute(collaborators, document)
    try:
        payload = diagnostics_io_actions.capture_state(document, request.object_names)
    except Exception as exc:
        return _failure(CaptureStateError("CAPTURE_STATE_FAILED", str(exc) or type(exc).__name__))
    objects_raw = payload["objects"]
    if not isinstance(objects_raw, dict):
        return _failure(CaptureStateError("CAPTURE_STATE_FAILED", "capture_state returned invalid objects payload"))
    parsed: dict[str, dict[str, object]] = {}
    for key, value in objects_raw.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        parsed[key] = {str(item_key): item_value for item_key, item_value in value.items()}
    return make_capture_state_success(str(payload["doc"]), parsed)


class _CaptureStateRpcFacade(Protocol):
    _cad_collaborators: CaptureStateCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_capture_state(
    self: _CaptureStateRpcFacade, doc_name: str, object_names: object = None
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_capture_state(collaborators, doc_name, object_names))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("capture_state", rpc_capture_state)


__all__ = [
    "CaptureStateCollaborators",
    "CaptureStateError",
    "build_capture_state_request",
    "rpc_capture_state",
    "run_capture_state",
    "TYPED_RPC_HANDLER",
]
