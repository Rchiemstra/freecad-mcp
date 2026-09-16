"""Typed ``get_sketch_geometry`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ...._shared.protocol.get_sketch_geometry_contract import (
    DocumentName,
    GetSketchGeometryCollaborators,
    GetSketchGeometryFailure,
    GetSketchGeometryRequest,
    GetSketchGeometryResult,
    SketchName,
    make_get_sketch_geometry_failure,
    make_get_sketch_geometry_success,
)
from . import assembly_io_actions
from .policy_runtime import app_from, lookup_document, lookup_object, optional_recompute
from .typed_runtime import as_int


class GetSketchGeometryError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: GetSketchGeometryError, *, retry_safe: bool = True) -> GetSketchGeometryFailure:
    return make_get_sketch_geometry_failure(error.code, str(error), retry_safe=retry_safe)


def build_get_sketch_geometry_request(
    doc_name: object,
    sketch_name: object,
    include_constraints: object,
    include_external: object,
    global_coords: object,
) -> GetSketchGeometryRequest | GetSketchGeometryFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(GetSketchGeometryError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(sketch_name, str) or not sketch_name.strip():
        return _failure(GetSketchGeometryError("INVALID_ARGUMENT", "sketch_name must be a nonempty string"))
    if type(include_constraints) is not bool:
        return _failure(GetSketchGeometryError("INVALID_ARGUMENT", "include_constraints must be a boolean"))
    if type(include_external) is not bool:
        return _failure(GetSketchGeometryError("INVALID_ARGUMENT", "include_external must be a boolean"))
    if type(global_coords) is not bool:
        return _failure(GetSketchGeometryError("INVALID_ARGUMENT", "global_coords must be a boolean"))
    return GetSketchGeometryRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        include_constraints=include_constraints,
        include_external=include_external,
        global_coords=global_coords,
    )


def run_get_sketch_geometry(
    collaborators: GetSketchGeometryCollaborators,
    doc_name: str,
    sketch_name: str,
    include_constraints: bool = True,
    include_external: bool = False,
    global_coords: bool = False,
) -> GetSketchGeometryResult:
    request = build_get_sketch_geometry_request(
        doc_name, sketch_name, include_constraints, include_external, global_coords
    )
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(GetSketchGeometryError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(GetSketchGeometryError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}"))
    if lookup_object(document, str(request.sketch_name)) is None:
        return _failure(GetSketchGeometryError("SKETCH_NOT_FOUND", "Sketch not found"))
    optional_recompute(collaborators, document)
    try:
        payload = assembly_io_actions.get_sketch_geometry(
            document,
            str(request.sketch_name),
            include_constraints=bool(request.include_constraints),
            include_external=bool(request.include_external),
            global_coords=bool(request.global_coords),
        )
    except Exception as exc:
        return _failure(GetSketchGeometryError("GET_SKETCH_GEOMETRY_FAILED", str(exc) or type(exc).__name__))
    return make_get_sketch_geometry_success(
        sketch_name=str(payload["sketch_name"]),
        geometry_count=as_int(payload["geometry_count"]),
        geometry=payload["geometry"],
        constraints=payload.get("constraints"),
        external_geometry=payload.get("external_geometry"),
    )


class _GetSketchGeometryRpcFacade(Protocol):
    _cad_collaborators: GetSketchGeometryCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_get_sketch_geometry(
    self: _GetSketchGeometryRpcFacade,
    doc_name: str,
    sketch_name: str,
    include_constraints: bool = True,
    include_external: bool = False,
    global_coords: bool = False,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_get_sketch_geometry(
            collaborators, doc_name, sketch_name, include_constraints, include_external, global_coords
        )
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("get_sketch_geometry", rpc_get_sketch_geometry)


__all__ = [
    "GetSketchGeometryCollaborators",
    "GetSketchGeometryError",
    "build_get_sketch_geometry_request",
    "rpc_get_sketch_geometry",
    "run_get_sketch_geometry",
    "TYPED_RPC_HANDLER",
]
