"""Typed ``set_color`` GUI handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ...._shared.protocol.set_color_contract import (
    DocumentName,
    ObjectName,
    SetColorCollaborators,
    SetColorFailure,
    SetColorRequest,
    SetColorResult,
    make_set_color_failure,
    make_set_color_success,
)
from .policy_runtime import app_from, lookup_document, lookup_object
from .typed_runtime import as_float


class SetColorError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: SetColorError, *, retry_safe: bool = True) -> SetColorFailure:
    return make_set_color_failure(error.code, str(error), retry_safe=retry_safe)


def build_set_color_request(
    doc_name: object,
    obj_name: object,
    r: object,
    g: object,
    b: object,
    transparency: object,
) -> SetColorRequest | SetColorFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(SetColorError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(obj_name, str) or not obj_name.strip():
        return _failure(SetColorError("INVALID_ARGUMENT", "obj_name must be a nonempty string"))
    for field, value in (("r", r), ("g", g), ("b", b), ("transparency", transparency)):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return _failure(SetColorError("INVALID_ARGUMENT", f"{field} must be a number"))
    return SetColorRequest(
        doc_name=DocumentName(doc_name),
        obj_name=ObjectName(obj_name),
        r=as_float(r),
        g=as_float(g),
        b=as_float(b),
        transparency=as_float(transparency),
    )


def run_set_color(
    collaborators: SetColorCollaborators,
    doc_name: str,
    obj_name: str,
    r: float,
    g: float,
    b: float,
    transparency: float = 0.0,
) -> SetColorResult:
    request = build_set_color_request(doc_name, obj_name, r, g, b, transparency)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(SetColorError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(SetColorError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}"))
    obj = lookup_object(document, str(request.obj_name))
    if obj is None:
        return _failure(SetColorError("OBJECT_NOT_FOUND", "Object not found"))
    view = getattr(obj, "ViewObject", None)
    if view is None:
        return _failure(SetColorError("VIEW_NOT_AVAILABLE", "Object has no ViewObject"))
    try:
        view.ShapeColor = (request.r, request.g, request.b, 1.0)
        view.Transparency = int(request.transparency * 100)
    except Exception as exc:
        return _failure(SetColorError("SET_COLOR_FAILED", str(exc) or type(exc).__name__))
    return make_set_color_success(
        str(getattr(obj, "Name", request.obj_name)),
        request.r,
        request.g,
        request.b,
        request.transparency,
    )


class _SetColorRpcFacade(Protocol):
    _cad_collaborators: SetColorCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_set_color(
    self: _SetColorRpcFacade,
    doc_name: str,
    obj_name: str,
    r: float,
    g: float,
    b: float,
    transparency: float = 0.0,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_set_color(collaborators, doc_name, obj_name, r, g, b, transparency)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("set_color", rpc_set_color)


__all__ = [
    "SetColorCollaborators",
    "SetColorError",
    "build_set_color_request",
    "rpc_set_color",
    "run_set_color",
    "TYPED_RPC_HANDLER",
]
