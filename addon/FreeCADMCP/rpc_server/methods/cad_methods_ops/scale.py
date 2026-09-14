"""Typed ``scale`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.scale_contract import (
    ObjectName,
    DocumentName,
    ScaleCollaborators,
    ScaleFailure,
    ScaleRequest,
    ScaleResult,
    MutationDocument,
    MutationObject,
    MutationReadDocument,
    make_scale_failure,
    make_scale_success,
    make_scale_uncertain,
)
from .typed_runtime import as_float, as_int, as_str
from . import measure_io_actions
from .scale_mutation import ScaleError, run_scale_native_mutation


@dataclass(frozen=True, slots=True)
class ScaleReceipt:
    payload: dict[str, object]
    obj: MutationObject | None


@dataclass(frozen=True, slots=True)
class ScaleInspection:
    payload: dict[str, object]


def _failure(error: ScaleError, *, retry_safe: bool = True) -> ScaleFailure:
    return make_scale_failure(error.code, str(error), retry_safe=retry_safe)


def build_scale_request(
    doc_name: object, obj_name: object, sx: object, sy: object, sz: object
) -> ScaleRequest | ScaleFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(ScaleError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(obj_name, str) or not obj_name.strip():
        return _failure(ScaleError("INVALID_ARGUMENT", "obj_name must be a nonempty string"))
    if isinstance(sx, bool) or not isinstance(sx, (int, float)):
        return _failure(ScaleError("INVALID_ARGUMENT", "sx must be a number"))
    if isinstance(sy, bool) or not isinstance(sy, (int, float)):
        return _failure(ScaleError("INVALID_ARGUMENT", "sy must be a number"))
    if isinstance(sz, bool) or not isinstance(sz, (int, float)):
        return _failure(ScaleError("INVALID_ARGUMENT", "sz must be a number"))
    request = ScaleRequest(
        doc_name=DocumentName(doc_name),
        obj_name=ObjectName(obj_name),
        sx=float(sx),
        sy=float(sy),
        sz=float(sz)
    )
    return request


@dataclass(slots=True)
class _ScaleExecution:
    collaborators: ScaleCollaborators
    request: ScaleRequest
    created: ScaleReceipt | None = None
    inspected: ScaleInspection | None = None

    def apply(self, doc: MutationDocument) -> None:
        self.created = apply_scale(doc, self.request)

    def inspect(self, doc: MutationReadDocument) -> None:
        if self.created is None:
            raise ScaleError(
                "INVALID_SCALE_RESULT",
                "scale did not return an identity receipt",
            )
        self.inspected = read_scale_result(doc, self.created, self.request)

    def run(self) -> ScaleResult:
        result = run_scale_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_scale_uncertain(
                "SCALE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected scale result",
                committed=True,
            )
        payload = self.inspected.payload
        return make_scale_success(
            object=as_str(payload["object"]), label=as_str(payload["label"])
        )


def apply_scale(doc: MutationDocument, request: ScaleRequest) -> ScaleReceipt:
    """Apply scale without recomputing or managing a transaction."""

    payload = measure_io_actions.scale(doc, request.obj_name, request.sx, request.sy, request.sz)
    target = payload.get("object")
    found = doc.getObject(str(target)) if isinstance(target, str) else None
    return ScaleReceipt(payload=dict(payload), obj=found)



def read_scale_result(
    doc: MutationReadDocument, receipt: ScaleReceipt, request: ScaleRequest
) -> ScaleInspection:
    key = "object"
    name = receipt.payload.get(key)
    if not isinstance(name, str) or not name.strip():
        raise ScaleError("INVALID_SCALE_RESULT", "missing created identity")
    obj = doc.getObject(name)
    if obj is None:
        raise ScaleError("CREATED_OBJECT_MISSING", f"Created object is missing: {name!r}")
    if receipt.obj is not None and obj is not receipt.obj:
        raise ScaleError("CREATED_OBJECT_REPLACED", f"Created object was replaced: {name!r}")

    payload = dict(receipt.payload)
    if hasattr(obj, "Label") and "label" in payload:
        payload["label"] = str(obj.Label)
    return ScaleInspection(payload=payload)



def run_scale(
    collaborators: ScaleCollaborators,
    doc_name: str, obj_name: str, sx: float, sy: float, sz: float,
) -> ScaleResult:
    """Run scale through apply, recompute, inspection, and commit."""

    request = build_scale_request(doc_name, obj_name, sx, sy, sz)
    if isinstance(request, dict):
        return request
    return _ScaleExecution(collaborators, request).run()


class _ScaleRpcFacade(Protocol):
    _cad_collaborators: ScaleCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_scale(
    self: _ScaleRpcFacade,
    doc_name: str, obj_name: str, sx: float, sy: float, sz: float,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_scale(collaborators, doc_name, obj_name, sx, sy, sz)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("scale", rpc_scale)


__all__ = [
    "ScaleCollaborators",
    "ScaleError",
    "ScaleInspection",
    "ScaleReceipt",
    "apply_scale",
    "build_scale_request",
    "read_scale_result",
    "rpc_scale",
    "run_scale",
    "TYPED_RPC_HANDLER",
]
