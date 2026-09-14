"""Typed ``bounding_box`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.bounding_box_contract import (
    ObjectName,
    DocumentName,
    BoundingBoxCollaborators,
    BoundingBoxFailure,
    BoundingBoxRequest,
    BoundingBoxResult,
    MutationDocument,
    MutationObject,
    MutationReadDocument,
    make_bounding_box_failure,
    make_bounding_box_success,
    make_bounding_box_uncertain,
)
from .typed_runtime import as_float, as_int, as_str
from . import measure_io_actions
from .bounding_box_mutation import BoundingBoxError, run_bounding_box_native_mutation


@dataclass(frozen=True, slots=True)
class BoundingBoxReceipt:
    payload: dict[str, object]
    obj: MutationObject | None


@dataclass(frozen=True, slots=True)
class BoundingBoxInspection:
    payload: dict[str, object]


def _failure(error: BoundingBoxError, *, retry_safe: bool = True) -> BoundingBoxFailure:
    return make_bounding_box_failure(error.code, str(error), retry_safe=retry_safe)


def build_bounding_box_request(
    doc_name: object, obj_name: object
) -> BoundingBoxRequest | BoundingBoxFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(BoundingBoxError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(obj_name, str) or not obj_name.strip():
        return _failure(BoundingBoxError("INVALID_ARGUMENT", "obj_name must be a nonempty string"))
    request = BoundingBoxRequest(
        doc_name=DocumentName(doc_name),
        obj_name=ObjectName(obj_name)
    )
    return request


@dataclass(slots=True)
class _BoundingBoxExecution:
    collaborators: BoundingBoxCollaborators
    request: BoundingBoxRequest
    created: BoundingBoxReceipt | None = None
    inspected: BoundingBoxInspection | None = None

    def apply(self, doc: MutationDocument) -> None:
        self.created = apply_bounding_box(doc, self.request)

    def inspect(self, doc: MutationReadDocument) -> None:
        if self.created is None:
            raise BoundingBoxError(
                "INVALID_BOUNDING_BOX_RESULT",
                "bounding_box did not return an identity receipt",
            )
        self.inspected = read_bounding_box_result(doc, self.created, self.request)

    def run(self) -> BoundingBoxResult:
        result = run_bounding_box_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_bounding_box_uncertain(
                "BOUNDING_BOX_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected bounding_box result",
                committed=True,
            )
        payload = self.inspected.payload
        return make_bounding_box_success(
            object=as_str(payload["object"]), xmin=as_float(payload["xmin"]), ymin=as_float(payload["ymin"]), zmin=as_float(payload["zmin"]), xmax=as_float(payload["xmax"]), ymax=as_float(payload["ymax"]), zmax=as_float(payload["zmax"]), dx=as_float(payload["dx"]), dy=as_float(payload["dy"]), dz=as_float(payload["dz"]), diagonal=as_float(payload["diagonal"]), frame=as_str(payload["frame"])
        )


def apply_bounding_box(doc: MutationDocument, request: BoundingBoxRequest) -> BoundingBoxReceipt:
    """Apply bounding_box without recomputing or managing a transaction."""

    obj = doc.getObject(request.obj_name)
    if obj is None:
        raise BoundingBoxError("OBJECT_NOT_FOUND", "Object not found")
    return BoundingBoxReceipt(payload={"object": obj.Name}, obj=obj)



def read_bounding_box_result(
    doc: MutationReadDocument, receipt: BoundingBoxReceipt, request: BoundingBoxRequest
) -> BoundingBoxInspection:
    payload = measure_io_actions.bounding_box(doc, request.obj_name)
    return BoundingBoxInspection(payload=payload)



def run_bounding_box(
    collaborators: BoundingBoxCollaborators,
    doc_name: str, obj_name: str,
) -> BoundingBoxResult:
    """Run bounding_box through apply, recompute, inspection, and commit."""

    request = build_bounding_box_request(doc_name, obj_name)
    if isinstance(request, dict):
        return request
    return _BoundingBoxExecution(collaborators, request).run()


class _BoundingBoxRpcFacade(Protocol):
    _cad_collaborators: BoundingBoxCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_bounding_box(
    self: _BoundingBoxRpcFacade,
    doc_name: str, obj_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_bounding_box(collaborators, doc_name, obj_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("bounding_box", rpc_bounding_box)


__all__ = [
    "BoundingBoxCollaborators",
    "BoundingBoxError",
    "BoundingBoxInspection",
    "BoundingBoxReceipt",
    "apply_bounding_box",
    "build_bounding_box_request",
    "read_bounding_box_result",
    "rpc_bounding_box",
    "run_bounding_box",
    "TYPED_RPC_HANDLER",
]
