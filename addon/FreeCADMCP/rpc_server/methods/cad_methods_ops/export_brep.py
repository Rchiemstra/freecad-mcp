"""Typed ``export_brep`` external-effect handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ...._shared.protocol.export_brep_contract import (
    DocumentName,
    ExportBrepCollaborators,
    ExportBrepFailure,
    ExportBrepRequest,
    ExportBrepResult,
    ObjectName,
    make_export_brep_failure,
    make_export_brep_success,
    make_export_brep_uncertain,
)
from . import measure_io_actions
from .policy_runtime import (
    app_from,
    atomic_publish,
    lookup_document,
    lookup_object,
    staged_path,
    unlink_quiet,
    verify_nonempty_file,
)
class ExportBrepError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: ExportBrepError, *, retry_safe: bool = True) -> ExportBrepFailure:
    return make_export_brep_failure(error.code, str(error), retry_safe=retry_safe)


def build_export_brep_request(
    doc_name: object, obj_name: object, file_path: object
) -> ExportBrepRequest | ExportBrepFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(ExportBrepError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(obj_name, str) or not obj_name.strip():
        return _failure(ExportBrepError("INVALID_ARGUMENT", "obj_name must be a nonempty string"))
    if not isinstance(file_path, str) or not file_path.strip():
        return _failure(ExportBrepError("INVALID_ARGUMENT", "file_path must be a nonempty string"))
    return ExportBrepRequest(
        doc_name=DocumentName(doc_name),
        obj_name=ObjectName(obj_name),
        file_path=file_path,
    )


def run_export_brep(
    collaborators: ExportBrepCollaborators,
    doc_name: str,
    obj_name: str,
    file_path: str,
) -> ExportBrepResult:
    request = build_export_brep_request(doc_name, obj_name, file_path)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(ExportBrepError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(ExportBrepError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}"))
    if lookup_object(document, str(request.obj_name)) is None:
        return _failure(ExportBrepError("OBJECT_NOT_FOUND", "Object not found"))
    tmp_path = staged_path(str(request.file_path))
    try:
        payload = measure_io_actions.export_brep(document, str(request.obj_name), tmp_path)
    except Exception as exc:
        unlink_quiet(tmp_path)
        return _failure(ExportBrepError("EXPORT_BREP_FAILED", str(exc) or type(exc).__name__))
    if not verify_nonempty_file(tmp_path):
        unlink_quiet(tmp_path)
        return _failure(ExportBrepError("EXPORT_BREP_FAILED", "Staged export file is missing or empty"))
    try:
        atomic_publish(tmp_path, str(request.file_path))
    except Exception as exc:
        unlink_quiet(tmp_path)
        if verify_nonempty_file(str(request.file_path)):
            return make_export_brep_uncertain(
                "EXPORT_BREP_PUBLISH_UNCERTAIN",
                str(exc) or type(exc).__name__,
                committed=None,
            )
        return _failure(ExportBrepError("EXPORT_BREP_FAILED", str(exc) or type(exc).__name__))
    return make_export_brep_success(
        path=str(request.file_path),
        exported=True,
        object=str(request.obj_name),
    )


class _ExportBrepRpcFacade(Protocol):
    _cad_collaborators: ExportBrepCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_export_brep(
    self: _ExportBrepRpcFacade,
    doc_name: str,
    obj_name: str,
    file_path: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_export_brep(collaborators, doc_name, obj_name, file_path)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("export_brep", rpc_export_brep)


__all__ = [
    "ExportBrepCollaborators",
    "ExportBrepError",
    "build_export_brep_request",
    "rpc_export_brep",
    "run_export_brep",
    "TYPED_RPC_HANDLER",
]
