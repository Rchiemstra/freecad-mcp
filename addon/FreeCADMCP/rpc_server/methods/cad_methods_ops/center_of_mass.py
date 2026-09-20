"""Typed ``center_of_mass`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

try:
    from ...._shared.protocol.center_of_mass_contract import (
        CenterOfMassCollaborators,
        CenterOfMassFailure,
        CenterOfMassRequest,
        CenterOfMassResult,
        DocumentName,
        ObjectName,
        make_center_of_mass_failure,
        make_center_of_mass_success,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.center_of_mass_contract import (
        CenterOfMassCollaborators,
        CenterOfMassFailure,
        CenterOfMassRequest,
        CenterOfMassResult,
        DocumentName,
        ObjectName,
        make_center_of_mass_failure,
        make_center_of_mass_success,
    )
from . import measure_io_actions
from .policy_runtime import app_from, lookup_document, lookup_object, optional_recompute
from .typed_runtime import as_float, as_str


class CenterOfMassError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: CenterOfMassError, *, retry_safe: bool = True) -> CenterOfMassFailure:
    return make_center_of_mass_failure(error.code, str(error), retry_safe=retry_safe)


def build_center_of_mass_request(
    doc_name: object, obj_name: object
) -> CenterOfMassRequest | CenterOfMassFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(CenterOfMassError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(obj_name, str) or not obj_name.strip():
        return _failure(CenterOfMassError("INVALID_ARGUMENT", "obj_name must be a nonempty string"))
    return CenterOfMassRequest(doc_name=DocumentName(doc_name), obj_name=ObjectName(obj_name))


def run_center_of_mass(
    collaborators: CenterOfMassCollaborators,
    doc_name: str,
    obj_name: str,
) -> CenterOfMassResult:
    request = build_center_of_mass_request(doc_name, obj_name)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(CenterOfMassError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(
            CenterOfMassError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}")
        )
    if lookup_object(document, str(request.obj_name)) is None:
        return _failure(CenterOfMassError("OBJECT_NOT_FOUND", "Object not found"))
    optional_recompute(collaborators, document)
    try:
        payload = measure_io_actions.center_of_mass(document, str(request.obj_name))
    except Exception as exc:
        return _failure(CenterOfMassError("CENTER_OF_MASS_FAILED", str(exc) or type(exc).__name__))
    return make_center_of_mass_success(
        object=as_str(payload["object"]),
        x=as_float(payload["x"]),
        y=as_float(payload["y"]),
        z=as_float(payload["z"]),
        unit=as_str(payload["unit"]),
        method=as_str(payload["method"]),
        frame=as_str(payload["frame"]),
    )


class _CenterOfMassRpcFacade(Protocol):
    _cad_collaborators: CenterOfMassCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_center_of_mass(
    self: _CenterOfMassRpcFacade,
    doc_name: str,
    obj_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_center_of_mass(collaborators, doc_name, obj_name))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("center_of_mass", rpc_center_of_mass)


__all__ = [
    "CenterOfMassCollaborators",
    "CenterOfMassError",
    "build_center_of_mass_request",
    "rpc_center_of_mass",
    "run_center_of_mass",
    "TYPED_RPC_HANDLER",
]
