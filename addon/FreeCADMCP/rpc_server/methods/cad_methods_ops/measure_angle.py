"""Typed ``measure_angle`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

try:
    from ...._shared.protocol.measure_angle_contract import (
        MeasureAngleCollaborators,
        MeasureAngleFailure,
        MeasureAngleRequest,
        MeasureAngleResult,
        DocumentName,
        ObjectName,
        make_measure_angle_failure,
        make_measure_angle_success,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.measure_angle_contract import (
        MeasureAngleCollaborators,
        MeasureAngleFailure,
        MeasureAngleRequest,
        MeasureAngleResult,
        DocumentName,
        ObjectName,
        make_measure_angle_failure,
        make_measure_angle_success,
    )
from . import measure_io_actions
from .policy_runtime import app_from, lookup_document, lookup_object, optional_recompute
from .typed_runtime import as_float, as_str


class MeasureAngleError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: MeasureAngleError, *, retry_safe: bool = True) -> MeasureAngleFailure:
    return make_measure_angle_failure(error.code, str(error), retry_safe=retry_safe)


def build_measure_angle_request(
    doc_name: object, edge1_ref: object, edge2_ref: object,
) -> MeasureAngleRequest | MeasureAngleFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(MeasureAngleError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(edge1_ref, str) or not edge1_ref.strip():
        return _failure(MeasureAngleError("INVALID_ARGUMENT", "edge1_ref must be a nonempty string"))
    if not isinstance(edge2_ref, str) or not edge2_ref.strip():
        return _failure(MeasureAngleError("INVALID_ARGUMENT", "edge2_ref must be a nonempty string"))
    return MeasureAngleRequest(doc_name=DocumentName(doc_name), edge1_ref=edge1_ref, edge2_ref=edge2_ref)


def run_measure_angle(
    collaborators: MeasureAngleCollaborators,
    doc_name: object, edge1_ref: object, edge2_ref: object,
) -> MeasureAngleResult:
    request = build_measure_angle_request(doc_name, edge1_ref, edge2_ref)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(MeasureAngleError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(MeasureAngleError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}"))
    edge1_object = str(request.edge1_ref).split(":", 1)[0]
    edge2_object = str(request.edge2_ref).split(":", 1)[0]
    if lookup_object(document, edge1_object) is None or lookup_object(document, edge2_object) is None:
        return _failure(MeasureAngleError("OBJECT_NOT_FOUND", "Object not found"))
    optional_recompute(collaborators, document)
    try:
        payload = measure_io_actions.measure_angle(document, str(request.edge1_ref), str(request.edge2_ref))
    except Exception as exc:
        return _failure(MeasureAngleError("MEASURE_ANGLE_FAILED", str(exc) or type(exc).__name__))
    return make_measure_angle_success(
        angle_deg=as_float(payload["angle_deg"]),
        unit=as_str(payload["unit"])
    )


class _MeasureAngleRpcFacade(Protocol):
    _cad_collaborators: MeasureAngleCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_measure_angle(
    self: _MeasureAngleRpcFacade,
    doc_name: str, edge1_ref: str, edge2_ref: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_measure_angle(collaborators, doc_name, edge1_ref, edge2_ref))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("measure_angle", rpc_measure_angle)


__all__ = [
    "MeasureAngleCollaborators",
    "MeasureAngleError",
    "build_measure_angle_request",
    "rpc_measure_angle",
    "run_measure_angle",
    "TYPED_RPC_HANDLER",
]
