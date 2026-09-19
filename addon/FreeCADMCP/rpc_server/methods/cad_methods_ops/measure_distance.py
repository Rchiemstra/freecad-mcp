"""Typed ``measure_distance`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

try:
    from ...._shared.protocol.measure_distance_contract import (
        MeasureDistanceCollaborators,
        MeasureDistanceFailure,
        MeasureDistanceRequest,
        MeasureDistanceResult,
        DocumentName,
        ObjectName,
        make_measure_distance_failure,
        make_measure_distance_success,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.measure_distance_contract import (
        MeasureDistanceCollaborators,
        MeasureDistanceFailure,
        MeasureDistanceRequest,
        MeasureDistanceResult,
        DocumentName,
        ObjectName,
        make_measure_distance_failure,
        make_measure_distance_success,
    )
from . import measure_io_actions
from .policy_runtime import app_from, lookup_document, lookup_object, optional_recompute
from .typed_runtime import as_float, as_str


class MeasureDistanceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: MeasureDistanceError, *, retry_safe: bool = True) -> MeasureDistanceFailure:
    return make_measure_distance_failure(error.code, str(error), retry_safe=retry_safe)


def build_measure_distance_request(
    doc_name: object, shape1_ref: object, shape2_ref: object,
) -> MeasureDistanceRequest | MeasureDistanceFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(MeasureDistanceError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(shape1_ref, str) or not shape1_ref.strip():
        return _failure(MeasureDistanceError("INVALID_ARGUMENT", "shape1_ref must be a nonempty string"))
    if not isinstance(shape2_ref, str) or not shape2_ref.strip():
        return _failure(MeasureDistanceError("INVALID_ARGUMENT", "shape2_ref must be a nonempty string"))
    return MeasureDistanceRequest(doc_name=DocumentName(doc_name), shape1_ref=shape1_ref, shape2_ref=shape2_ref)


def run_measure_distance(
    collaborators: MeasureDistanceCollaborators,
    doc_name: object, shape1_ref: object, shape2_ref: object,
) -> MeasureDistanceResult:
    request = build_measure_distance_request(doc_name, shape1_ref, shape2_ref)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(MeasureDistanceError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(MeasureDistanceError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}"))
    if lookup_object(document, str(request.shape1_ref)) is None or lookup_object(document, str(request.shape2_ref)) is None:
        return _failure(MeasureDistanceError("OBJECT_NOT_FOUND", "Object not found"))
    optional_recompute(collaborators, document)
    try:
        payload = measure_io_actions.measure_distance(document, str(request.shape1_ref), str(request.shape2_ref))
    except Exception as exc:
        return _failure(MeasureDistanceError("MEASURE_DISTANCE_FAILED", str(exc) or type(exc).__name__))
    return make_measure_distance_success(
        distance=as_float(payload["distance"]),
        unit=as_str(payload["unit"])
    )


class _MeasureDistanceRpcFacade(Protocol):
    _cad_collaborators: MeasureDistanceCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_measure_distance(
    self: _MeasureDistanceRpcFacade,
    doc_name: str, shape1_ref: str, shape2_ref: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_measure_distance(collaborators, doc_name, shape1_ref, shape2_ref))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("measure_distance", rpc_measure_distance)


__all__ = [
    "MeasureDistanceCollaborators",
    "MeasureDistanceError",
    "build_measure_distance_request",
    "rpc_measure_distance",
    "run_measure_distance",
    "TYPED_RPC_HANDLER",
]
