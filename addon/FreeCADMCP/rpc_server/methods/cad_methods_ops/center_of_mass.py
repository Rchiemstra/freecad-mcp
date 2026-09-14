"""Typed ``center_of_mass`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.center_of_mass_contract import (
    ObjectName,
    DocumentName,
    CenterOfMassCollaborators,
    CenterOfMassFailure,
    CenterOfMassRequest,
    CenterOfMassResult,
    MutationDocument,
    MutationObject,
    MutationReadDocument,
    make_center_of_mass_failure,
    make_center_of_mass_success,
    make_center_of_mass_uncertain,
)
from .typed_runtime import as_float, as_int, as_str
from . import measure_io_actions
from .center_of_mass_mutation import CenterOfMassError, run_center_of_mass_native_mutation


@dataclass(frozen=True, slots=True)
class CenterOfMassReceipt:
    payload: dict[str, object]
    obj: MutationObject | None


@dataclass(frozen=True, slots=True)
class CenterOfMassInspection:
    payload: dict[str, object]


def _failure(error: CenterOfMassError, *, retry_safe: bool = True) -> CenterOfMassFailure:
    return make_center_of_mass_failure(error.code, str(error), retry_safe=retry_safe)


def build_center_of_mass_request(
    doc_name: object, obj_name: object
) -> CenterOfMassRequest | CenterOfMassFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(CenterOfMassError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(obj_name, str) or not obj_name.strip():
        return _failure(CenterOfMassError("INVALID_ARGUMENT", "obj_name must be a nonempty string"))
    request = CenterOfMassRequest(
        doc_name=DocumentName(doc_name),
        obj_name=ObjectName(obj_name)
    )
    return request


@dataclass(slots=True)
class _CenterOfMassExecution:
    collaborators: CenterOfMassCollaborators
    request: CenterOfMassRequest
    created: CenterOfMassReceipt | None = None
    inspected: CenterOfMassInspection | None = None

    def apply(self, doc: MutationDocument) -> None:
        self.created = apply_center_of_mass(doc, self.request)

    def inspect(self, doc: MutationReadDocument) -> None:
        if self.created is None:
            raise CenterOfMassError(
                "INVALID_CENTER_OF_MASS_RESULT",
                "center_of_mass did not return an identity receipt",
            )
        self.inspected = read_center_of_mass_result(doc, self.created, self.request)

    def run(self) -> CenterOfMassResult:
        result = run_center_of_mass_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_center_of_mass_uncertain(
                "CENTER_OF_MASS_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected center_of_mass result",
                committed=True,
            )
        payload = self.inspected.payload
        return make_center_of_mass_success(
            object=as_str(payload["object"]), x=as_float(payload["x"]), y=as_float(payload["y"]), z=as_float(payload["z"]), unit=as_str(payload["unit"]), method=as_str(payload["method"]), frame=as_str(payload["frame"])
        )


def apply_center_of_mass(doc: MutationDocument, request: CenterOfMassRequest) -> CenterOfMassReceipt:
    """Apply center_of_mass without recomputing or managing a transaction."""

    obj = doc.getObject(request.obj_name)
    if obj is None:
        raise CenterOfMassError("OBJECT_NOT_FOUND", "Object not found")
    return CenterOfMassReceipt(payload={"object": obj.Name}, obj=obj)



def read_center_of_mass_result(
    doc: MutationReadDocument, receipt: CenterOfMassReceipt, request: CenterOfMassRequest
) -> CenterOfMassInspection:
    payload = measure_io_actions.center_of_mass(doc, request.obj_name)
    return CenterOfMassInspection(payload=payload)



def run_center_of_mass(
    collaborators: CenterOfMassCollaborators,
    doc_name: str, obj_name: str,
) -> CenterOfMassResult:
    """Run center_of_mass through apply, recompute, inspection, and commit."""

    request = build_center_of_mass_request(doc_name, obj_name)
    if isinstance(request, dict):
        return request
    return _CenterOfMassExecution(collaborators, request).run()


class _CenterOfMassRpcFacade(Protocol):
    _cad_collaborators: CenterOfMassCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_center_of_mass(
    self: _CenterOfMassRpcFacade,
    doc_name: str, obj_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_center_of_mass(collaborators, doc_name, obj_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("center_of_mass", rpc_center_of_mass)


__all__ = [
    "CenterOfMassCollaborators",
    "CenterOfMassError",
    "CenterOfMassInspection",
    "CenterOfMassReceipt",
    "apply_center_of_mass",
    "build_center_of_mass_request",
    "read_center_of_mass_result",
    "rpc_center_of_mass",
    "run_center_of_mass",
    "TYPED_RPC_HANDLER",
]
