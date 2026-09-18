"""Typed ``measure_area`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

try:
    from ...._shared.protocol.measure_area_contract import (
        MeasureAreaCollaborators,
        MeasureAreaFailure,
        MeasureAreaRequest,
        MeasureAreaResult,
        DocumentName,
        ObjectName,
        make_measure_area_failure,
        make_measure_area_success,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.measure_area_contract import (
        MeasureAreaCollaborators,
        MeasureAreaFailure,
        MeasureAreaRequest,
        MeasureAreaResult,
        DocumentName,
        ObjectName,
        make_measure_area_failure,
        make_measure_area_success,
    )
from . import measure_io_actions
from .policy_runtime import app_from, lookup_document, lookup_object, optional_recompute
from .typed_runtime import as_float, as_str


class MeasureAreaError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: MeasureAreaError, *, retry_safe: bool = True) -> MeasureAreaFailure:
    return make_measure_area_failure(error.code, str(error), retry_safe=retry_safe)


def build_measure_area_request(
    doc_name: object, obj_name: object,
) -> MeasureAreaRequest | MeasureAreaFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(MeasureAreaError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(obj_name, str) or not obj_name.strip():
        return _failure(MeasureAreaError("INVALID_ARGUMENT", "obj_name must be a nonempty string"))
    return MeasureAreaRequest(doc_name=DocumentName(doc_name), obj_name=ObjectName(obj_name))


def run_measure_area(
    collaborators: MeasureAreaCollaborators,
    doc_name: object, obj_name: object,
) -> MeasureAreaResult:
    request = build_measure_area_request(doc_name, obj_name)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(MeasureAreaError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(MeasureAreaError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}"))
    if lookup_object(document, str(request.obj_name)) is None:
        return _failure(MeasureAreaError("OBJECT_NOT_FOUND", "Object not found"))
    optional_recompute(collaborators, document)
    try:
        payload = measure_io_actions.measure_area(document, str(request.obj_name))
    except Exception as exc:
        return _failure(MeasureAreaError("MEASURE_AREA_FAILED", str(exc) or type(exc).__name__))
    return make_measure_area_success(
        object=as_str(payload["object"]),
        area_mm2=as_float(payload["area_mm2"]),
        area_cm2=as_float(payload["area_cm2"]),
        unit=as_str(payload["unit"]),
        frame=as_str(payload["frame"])
    )


class _MeasureAreaRpcFacade(Protocol):
    _cad_collaborators: MeasureAreaCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_measure_area(
    self: _MeasureAreaRpcFacade,
    doc_name: str, obj_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_measure_area(collaborators, doc_name, obj_name))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("measure_area", rpc_measure_area)


__all__ = [
    "MeasureAreaCollaborators",
    "MeasureAreaError",
    "build_measure_area_request",
    "rpc_measure_area",
    "run_measure_area",
    "TYPED_RPC_HANDLER",
]
