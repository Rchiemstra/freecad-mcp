"""Typed ``export_step`` external-effect handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

try:
    from ...._shared.protocol.export_step_contract import (
        DocumentName,
        ExportStepCollaborators,
        ExportStepFailure,
        ExportStepRequest,
        ExportStepResult,
        make_export_step_failure,
        make_export_step_success,
        make_export_step_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.export_step_contract import (
        DocumentName,
        ExportStepCollaborators,
        ExportStepFailure,
        ExportStepRequest,
        ExportStepResult,
        make_export_step_failure,
        make_export_step_success,
        make_export_step_uncertain,
    )
from . import measure_io_actions
from .policy_runtime import (
    app_from,
    atomic_publish,
    lookup_document,
    staged_path,
    unlink_quiet,
    verify_nonempty_file,
)
from .typed_runtime import as_int


class ExportStepError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: ExportStepError, *, retry_safe: bool = True) -> ExportStepFailure:
    return make_export_step_failure(error.code, str(error), retry_safe=retry_safe)


def build_export_step_request(
    doc_name: object, file_path: object, obj_names: object
) -> ExportStepRequest | ExportStepFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(ExportStepError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(file_path, str) or not file_path.strip():
        return _failure(ExportStepError("INVALID_ARGUMENT", "file_path must be a nonempty string"))
    if obj_names is None:
        obj_names_value: list[str] | None = None
    elif not isinstance(obj_names, list) or any(not isinstance(item, str) for item in obj_names):
        return _failure(ExportStepError("INVALID_ARGUMENT", "obj_names must be a list of strings"))
    else:
        obj_names_value = obj_names
    return ExportStepRequest(
        doc_name=DocumentName(doc_name),
        file_path=file_path,
        obj_names=obj_names_value,
    )


def run_export_step(
    collaborators: ExportStepCollaborators,
    doc_name: str,
    file_path: str,
    obj_names: list[str] | None = None,
) -> ExportStepResult:
    request = build_export_step_request(doc_name, file_path, obj_names)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(ExportStepError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(ExportStepError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}"))
    tmp_path = staged_path(str(request.file_path))
    try:
        payload = measure_io_actions.export_step(document, tmp_path, request.obj_names)
    except Exception as exc:
        unlink_quiet(tmp_path)
        return _failure(ExportStepError("EXPORT_STEP_FAILED", str(exc) or type(exc).__name__))
    if not verify_nonempty_file(tmp_path):
        unlink_quiet(tmp_path)
        return _failure(ExportStepError("EXPORT_STEP_FAILED", "Staged export file is missing or empty"))
    try:
        atomic_publish(tmp_path, str(request.file_path))
    except Exception as exc:
        unlink_quiet(tmp_path)
        if verify_nonempty_file(str(request.file_path)):
            return make_export_step_uncertain(
                "EXPORT_STEP_PUBLISH_UNCERTAIN",
                str(exc) or type(exc).__name__,
                committed=None,
            )
        return _failure(ExportStepError("EXPORT_STEP_FAILED", str(exc) or type(exc).__name__))
    return make_export_step_success(
        path=str(request.file_path),
        exported=as_int(payload.get("exported", 0)),
    )


class _ExportStepRpcFacade(Protocol):
    _cad_collaborators: ExportStepCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_export_step(
    self: _ExportStepRpcFacade,
    doc_name: str,
    file_path: str,
    obj_names: list[str] | None = None,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_export_step(collaborators, doc_name, file_path, obj_names)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("export_step", rpc_export_step)


__all__ = [
    "ExportStepCollaborators",
    "ExportStepError",
    "build_export_step_request",
    "rpc_export_step",
    "run_export_step",
    "TYPED_RPC_HANDLER",
]
