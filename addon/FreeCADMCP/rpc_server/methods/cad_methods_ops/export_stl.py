"""Typed ``export_stl`` external-effect handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ...._shared.protocol.export_stl_contract import (
    DocumentName,
    ExportStlCollaborators,
    ExportStlFailure,
    ExportStlRequest,
    ExportStlResult,
    make_export_stl_failure,
    make_export_stl_success,
    make_export_stl_uncertain,
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


class ExportStlError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: ExportStlError, *, retry_safe: bool = True) -> ExportStlFailure:
    return make_export_stl_failure(error.code, str(error), retry_safe=retry_safe)


def build_export_stl_request(
    doc_name: object, file_path: object, obj_names: object, mesh_deviation: object
) -> ExportStlRequest | ExportStlFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(ExportStlError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(file_path, str) or not file_path.strip():
        return _failure(ExportStlError("INVALID_ARGUMENT", "file_path must be a nonempty string"))
    if obj_names is None:
        obj_names_value: list[str] | None = None
    elif not isinstance(obj_names, list) or any(not isinstance(item, str) for item in obj_names):
        return _failure(ExportStlError("INVALID_ARGUMENT", "obj_names must be a list of strings"))
    else:
        obj_names_value = obj_names
    if mesh_deviation is None:
        mesh_deviation_value = float(0.1)
    elif isinstance(mesh_deviation, bool) or not isinstance(mesh_deviation, (int, float)):
        return _failure(ExportStlError("INVALID_ARGUMENT", "mesh_deviation must be a number"))
    else:
        mesh_deviation_value = float(mesh_deviation)
    return ExportStlRequest(
        doc_name=DocumentName(doc_name),
        file_path=file_path,
        obj_names=obj_names_value,
        mesh_deviation=mesh_deviation_value,
    )


def run_export_stl(
    collaborators: ExportStlCollaborators,
    doc_name: str,
    file_path: str,
    obj_names: list[str] | None = None,
    mesh_deviation: float = 0.1,
) -> ExportStlResult:
    request = build_export_stl_request(doc_name, file_path, obj_names, mesh_deviation)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(ExportStlError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(ExportStlError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}"))
    tmp_path = staged_path(str(request.file_path))
    try:
        payload = measure_io_actions.export_stl(
            document, tmp_path, request.obj_names, request.mesh_deviation
        )
    except Exception as exc:
        unlink_quiet(tmp_path)
        return _failure(ExportStlError("EXPORT_STL_FAILED", str(exc) or type(exc).__name__))
    if not verify_nonempty_file(tmp_path):
        unlink_quiet(tmp_path)
        return _failure(ExportStlError("EXPORT_STL_FAILED", "Staged export file is missing or empty"))
    try:
        atomic_publish(tmp_path, str(request.file_path))
    except Exception as exc:
        unlink_quiet(tmp_path)
        if verify_nonempty_file(str(request.file_path)):
            return make_export_stl_uncertain(
                "EXPORT_STL_PUBLISH_UNCERTAIN",
                str(exc) or type(exc).__name__,
                committed=None,
            )
        return _failure(ExportStlError("EXPORT_STL_FAILED", str(exc) or type(exc).__name__))
    return make_export_stl_success(
        path=str(request.file_path),
        exported=as_int(payload.get("exported", 0)),
        faces=as_int(payload.get("faces", 0)),
    )


class _ExportStlRpcFacade(Protocol):
    _cad_collaborators: ExportStlCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_export_stl(
    self: _ExportStlRpcFacade,
    doc_name: str,
    file_path: str,
    obj_names: list[str] | None = None,
    mesh_deviation: float = 0.1,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_export_stl(collaborators, doc_name, file_path, obj_names, mesh_deviation)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("export_stl", rpc_export_stl)


__all__ = [
    "ExportStlCollaborators",
    "ExportStlError",
    "build_export_stl_request",
    "rpc_export_stl",
    "run_export_stl",
    "TYPED_RPC_HANDLER",
]
