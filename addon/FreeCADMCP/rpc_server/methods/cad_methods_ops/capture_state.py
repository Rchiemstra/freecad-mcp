"""Typed ``capture_state`` mutation."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.capture_state_contract import (
    CaptureStateCollaborators,
    CaptureStateDocument,
    CaptureStateFailure,
    CaptureStateName,
    CaptureStateReadDocument,
    CaptureStateRequest,
    CaptureStateResult,
    DocumentName,
    make_capture_state_failure,
    make_capture_state_success,
    make_capture_state_uncertain,
)
from .capture_state_mutation import CaptureStateError, run_capture_state_native_mutation
from .typed_rpc_support import (
    nonempty_string,
    object_label,
    object_name,
    object_type_id,
)


@dataclass(frozen=True, slots=True)
class CaptureStateReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    skipped: bool = False
    extra: object = None


@dataclass(frozen=True, slots=True)
class CaptureStateInspection:
    """Read-only data captured after the native-owned recompute."""

    name: CaptureStateName
    label: str
    extra: object = None


def _failure(error: CaptureStateError, *, retry_safe: bool = True) -> CaptureStateFailure:
    return make_capture_state_failure(error.code, str(error), retry_safe=retry_safe)


def _iter_document_objects(doc: CaptureStateDocument) -> Iterable[object]:
    objects = getattr(doc, "Objects", None)
    if objects is None:
        return ()
    if isinstance(objects, (list, tuple)):
        return objects
    return ()


def _capture_object_state(obj: object) -> dict[str, object]:
    state: dict[str, object] = {"name": object_name(obj) or ""}
    type_id = object_type_id(obj)
    if type_id:
        state["type_id"] = type_id
    label = object_label(obj)
    if label:
        state["label"] = label
    placement = getattr(obj, "Placement", None)
    base = getattr(placement, "Base", None) if placement is not None else None
    if base is not None:
        state["placement"] = {
            "x": float(getattr(base, "x", 0.0)),
            "y": float(getattr(base, "y", 0.0)),
            "z": float(getattr(base, "z", 0.0)),
        }
    shape = getattr(obj, "Shape", None)
    if shape is not None:
        bbox = getattr(shape, "BoundBox", None)
        if bbox is not None:
            state["bbox"] = {
                "min": {
                    "x": float(getattr(bbox, "XMin", 0.0)),
                    "y": float(getattr(bbox, "YMin", 0.0)),
                    "z": float(getattr(bbox, "ZMin", 0.0)),
                },
                "max": {
                    "x": float(getattr(bbox, "XMax", 0.0)),
                    "y": float(getattr(bbox, "YMax", 0.0)),
                    "z": float(getattr(bbox, "ZMax", 0.0)),
                },
            }
        faces = getattr(shape, "Faces", None)
        if faces is not None:
            state["face_count"] = len(faces)
        edges = getattr(shape, "Edges", None)
        if edges is not None:
            state["edge_count"] = len(edges)
    return state


def apply_capture_state(doc: CaptureStateDocument, request: CaptureStateRequest) -> CaptureStateReceipt:
    """Record which objects will be inspected after native recompute."""

    if request.object_names is None:
        names = [object_name(item) for item in _iter_document_objects(doc)]
        names = [name for name in names if isinstance(name, str) and name]
    else:
        names = list(request.object_names)
    return CaptureStateReceipt(
        name=str(getattr(doc, "Name", "") or request.doc_name),
        item=doc,
        skipped=False,
        extra=names,
    )


def read_capture_state_result(doc: CaptureStateReadDocument, receipt: CaptureStateReceipt) -> CaptureStateInspection:
    """Capture geometry for the requested objects after native recompute."""

    names = receipt.extra if isinstance(receipt.extra, list) else []
    objects: dict[str, dict[str, object]] = {}
    for name in names:
        if not isinstance(name, str) or not name:
            continue
        located = doc.getObject(name)
        if located is None:
            raise CaptureStateError("OBJECT_NOT_FOUND", f"Object is missing: {name!r}")
        objects[name] = _capture_object_state(located)
    return CaptureStateInspection(
        name=CaptureStateName(receipt.name),
        label=receipt.name,
        extra=objects,
    )


def build_capture_state_request(doc_name: object, object_names: object) -> CaptureStateRequest | CaptureStateFailure:
    doc_name_value = nonempty_string(doc_name, 'doc_name')
    if doc_name_value is None:
        return _failure(CaptureStateError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if object_names is not None:
        if not isinstance(object_names, list):
            return _failure(CaptureStateError("INVALID_ARGUMENT", "object_names must be a list of strings or None"))
        for name in object_names:
            if not isinstance(name, str) or not name.strip():
                return _failure(CaptureStateError("INVALID_ARGUMENT", "object_names must contain nonempty strings"))
    return CaptureStateRequest(
        doc_name=DocumentName(doc_name_value),
        object_names=object_names,
    )


@dataclass(slots=True)
class _CaptureStateExecution:
    collaborators: CaptureStateCollaborators
    request: CaptureStateRequest
    created: CaptureStateReceipt | None = None
    inspected: CaptureStateInspection | None = None

    def apply(self, doc: CaptureStateDocument) -> None:
        self.created = apply_capture_state(doc, self.request)

    def inspect(self, doc: CaptureStateReadDocument) -> None:
        if self.created is None:
            raise CaptureStateError(
                "INVALID_CAPTURE_STATE_RESULT",
                "capture_state did not return an identity receipt",
            )
        self.inspected = read_capture_state_result(doc, self.created)

    def run(self) -> CaptureStateResult:
        result = run_capture_state_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_capture_state_uncertain(
                "CAPTURE_STATE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        objects = self.inspected.extra
        if not isinstance(objects, dict):
            objects = {}
        return make_capture_state_success(doc=str(self.request.doc_name), objects=objects)


def run_capture_state(
    collaborators: CaptureStateCollaborators,
    doc_name: object, object_names: object,
) -> CaptureStateResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_capture_state_request(doc_name, object_names)
    if isinstance(request, dict):
        return request
    return _CaptureStateExecution(collaborators, request).run()


class _CaptureStateRpcFacade(Protocol):
    _cad_collaborators: CaptureStateCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_capture_state(
    self: _CaptureStateRpcFacade, doc_name: str, object_names: object = None,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_capture_state(collaborators, doc_name, object_names)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("capture_state", rpc_capture_state)


__all__ = [
    "CaptureStateCollaborators",
    "CaptureStateError",
    "CaptureStateInspection",
    "CaptureStateReceipt",
    "apply_capture_state",
    "build_capture_state_request",
    "read_capture_state_result",
    "rpc_capture_state",
    "run_capture_state",
    "TYPED_RPC_HANDLER",
]
