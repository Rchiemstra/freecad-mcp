"""Typed ``measure_volume`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ...._shared.protocol.measure_volume_contract import (
    MeasureVolumeCollaborators,
    MeasureVolumeFailure,
    MeasureVolumeRequest,
    MeasureVolumeResult,
    DocumentName,
    ObjectName,
    make_measure_volume_failure,
    make_measure_volume_success,
)
from . import measure_io_actions
from .policy_runtime import app_from, lookup_document, lookup_object, optional_recompute
from .typed_runtime import TypedMutationError, as_float, as_str


class MeasureVolumeError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: MeasureVolumeError, *, retry_safe: bool = True) -> MeasureVolumeFailure:
    return make_measure_volume_failure(error.code, str(error), retry_safe=retry_safe)


def build_measure_volume_request(
    doc_name: object, obj_name: object,
) -> MeasureVolumeRequest | MeasureVolumeFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(MeasureVolumeError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(obj_name, str) or not obj_name.strip():
        return _failure(MeasureVolumeError("INVALID_ARGUMENT", "obj_name must be a nonempty string"))
    return MeasureVolumeRequest(doc_name=DocumentName(doc_name), obj_name=ObjectName(obj_name))


def run_measure_volume(
    collaborators: MeasureVolumeCollaborators,
    doc_name: object, obj_name: object,
) -> MeasureVolumeResult:
    request = build_measure_volume_request(doc_name, obj_name)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(MeasureVolumeError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(MeasureVolumeError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}"))
    if lookup_object(document, str(request.obj_name)) is None:
        return _failure(MeasureVolumeError("OBJECT_NOT_FOUND", "Object not found"))
    optional_recompute(collaborators, document)
    try:
        payload = measure_io_actions.measure_volume(document, str(request.obj_name))
    except TypedMutationError as exc:
        return _failure(MeasureVolumeError(exc.code, str(exc)))
    except Exception as exc:
        return _failure(MeasureVolumeError("MEASURE_VOLUME_FAILED", str(exc) or type(exc).__name__))
    return make_measure_volume_success(
        object=as_str(payload["object"]),
        volume_mm3=as_float(payload["volume_mm3"]),
        unit=as_str(payload["unit"]),
        frame=as_str(payload["frame"]),
        used_linked_object=bool(payload.get("used_linked_object", False)),
    )


class _MeasureVolumeRpcFacade(Protocol):
    _cad_collaborators: MeasureVolumeCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_measure_volume(
    self: _MeasureVolumeRpcFacade,
    doc_name: str, obj_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_measure_volume(collaborators, doc_name, obj_name))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("measure_volume", rpc_measure_volume)


__all__ = [
    "MeasureVolumeCollaborators",
    "MeasureVolumeError",
    "build_measure_volume_request",
    "rpc_measure_volume",
    "run_measure_volume",
    "TYPED_RPC_HANDLER",
]
