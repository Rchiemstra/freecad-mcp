"""Typed ``create_assembly_grounded_joint`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.create_assembly_grounded_joint_contract import (
    DocumentName,
    ComponentName,
    AssemblyName,
    CreateAssemblyGroundedJointCollaborators,
    CreateAssemblyGroundedJointFailure,
    CreateAssemblyGroundedJointRequest,
    CreateAssemblyGroundedJointResult,
    MutationDocument,
    MutationObject,
    MutationReadDocument,
    make_create_assembly_grounded_joint_failure,
    make_create_assembly_grounded_joint_success,
    make_create_assembly_grounded_joint_uncertain,
)
from .typed_runtime import as_float, as_int, as_str
from . import assembly_actions
from .create_assembly_grounded_joint_mutation import CreateAssemblyGroundedJointError, run_create_assembly_grounded_joint_native_mutation


@dataclass(frozen=True, slots=True)
class CreateAssemblyGroundedJointReceipt:
    payload: dict[str, object]
    obj: MutationObject | None


@dataclass(frozen=True, slots=True)
class CreateAssemblyGroundedJointInspection:
    payload: dict[str, object]


def _failure(error: CreateAssemblyGroundedJointError, *, retry_safe: bool = True) -> CreateAssemblyGroundedJointFailure:
    return make_create_assembly_grounded_joint_failure(error.code, str(error), retry_safe=retry_safe)


def build_create_assembly_grounded_joint_request(
    doc_name: object, assembly_name: object, component_name: object, label: object, recompute: object
) -> CreateAssemblyGroundedJointRequest | CreateAssemblyGroundedJointFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(CreateAssemblyGroundedJointError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(assembly_name, str) or not assembly_name.strip():
        return _failure(CreateAssemblyGroundedJointError("INVALID_ARGUMENT", "assembly_name must be a nonempty string"))
    if not isinstance(component_name, str) or not component_name.strip():
        return _failure(CreateAssemblyGroundedJointError("INVALID_ARGUMENT", "component_name must be a nonempty string"))
    if label is None:
        label_value: str | None = None
    elif not isinstance(label, str):
        return _failure(CreateAssemblyGroundedJointError("INVALID_ARGUMENT", "label must be a string or null"))
    else:
        label_value = label
    if recompute is None:
        recompute_value = True
    elif not isinstance(recompute, bool):
        return _failure(CreateAssemblyGroundedJointError("INVALID_ARGUMENT", "recompute must be a boolean"))
    else:
        recompute_value = recompute
    request = CreateAssemblyGroundedJointRequest(
        doc_name=DocumentName(doc_name),
        assembly_name=AssemblyName(assembly_name),
        component_name=ComponentName(component_name),
        label=label_value,
        recompute=recompute_value
    )
    return request


@dataclass(slots=True)
class _CreateAssemblyGroundedJointExecution:
    collaborators: CreateAssemblyGroundedJointCollaborators
    request: CreateAssemblyGroundedJointRequest
    created: CreateAssemblyGroundedJointReceipt | None = None
    inspected: CreateAssemblyGroundedJointInspection | None = None

    def apply(self, doc: MutationDocument) -> None:
        self.created = apply_create_assembly_grounded_joint(doc, self.request)

    def inspect(self, doc: MutationReadDocument) -> None:
        if self.created is None:
            raise CreateAssemblyGroundedJointError(
                "INVALID_CREATE_ASSEMBLY_GROUNDED_JOINT_RESULT",
                "create_assembly_grounded_joint did not return an identity receipt",
            )
        self.inspected = read_create_assembly_grounded_joint_result(doc, self.created, self.request)

    def run(self) -> CreateAssemblyGroundedJointResult:
        result = run_create_assembly_grounded_joint_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_create_assembly_grounded_joint_uncertain(
                "CREATE_ASSEMBLY_GROUNDED_JOINT_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected create_assembly_grounded_joint result",
                committed=True,
            )
        payload = self.inspected.payload
        return make_create_assembly_grounded_joint_success(
            joint=as_str(payload["joint"]), label=as_str(payload["label"]), joint_type=as_str(payload["joint_type"]), assembly=as_str(payload["assembly"]), component=as_str(payload["component"])
        )


def apply_create_assembly_grounded_joint(doc: MutationDocument, request: CreateAssemblyGroundedJointRequest) -> CreateAssemblyGroundedJointReceipt:
    """Apply create_assembly_grounded_joint without recomputing or managing a transaction."""

    payload = assembly_actions.create_grounded_joint(doc, assembly_name=request.assembly_name, component_name=request.component_name, label=request.label)
    target = payload.get("joint")
    found = doc.getObject(str(target)) if isinstance(target, str) else None
    return CreateAssemblyGroundedJointReceipt(payload=dict(payload), obj=found)



def read_create_assembly_grounded_joint_result(
    doc: MutationReadDocument, receipt: CreateAssemblyGroundedJointReceipt, request: CreateAssemblyGroundedJointRequest
) -> CreateAssemblyGroundedJointInspection:
    key = "joint"
    name = receipt.payload.get(key)
    if not isinstance(name, str) or not name.strip():
        raise CreateAssemblyGroundedJointError("INVALID_CREATE_ASSEMBLY_GROUNDED_JOINT_RESULT", "missing created identity")
    obj = doc.getObject(name)
    if obj is None:
        raise CreateAssemblyGroundedJointError("CREATED_OBJECT_MISSING", f"Created object is missing: {name!r}")
    if receipt.obj is not None and obj is not receipt.obj:
        raise CreateAssemblyGroundedJointError("CREATED_OBJECT_REPLACED", f"Created object was replaced: {name!r}")

    payload = dict(receipt.payload)
    if hasattr(obj, "Label") and "label" in payload:
        payload["label"] = str(obj.Label)
    return CreateAssemblyGroundedJointInspection(payload=payload)



def run_create_assembly_grounded_joint(
    collaborators: CreateAssemblyGroundedJointCollaborators,
    doc_name: str, assembly_name: str, component_name: str, label: str | None = None, recompute: bool = True,
) -> CreateAssemblyGroundedJointResult:
    """Run create_assembly_grounded_joint through apply, recompute, inspection, and commit."""

    request = build_create_assembly_grounded_joint_request(doc_name, assembly_name, component_name, label, recompute)
    if isinstance(request, dict):
        return request
    return _CreateAssemblyGroundedJointExecution(collaborators, request).run()


class _CreateAssemblyGroundedJointRpcFacade(Protocol):
    _cad_collaborators: CreateAssemblyGroundedJointCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_create_assembly_grounded_joint(
    self: _CreateAssemblyGroundedJointRpcFacade,
    doc_name: str, assembly_name: str, component_name: str, label: str | None = None, recompute: bool = True,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_create_assembly_grounded_joint(collaborators, doc_name, assembly_name, component_name, label, recompute)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("create_assembly_grounded_joint", rpc_create_assembly_grounded_joint)


__all__ = [
    "CreateAssemblyGroundedJointCollaborators",
    "CreateAssemblyGroundedJointError",
    "CreateAssemblyGroundedJointInspection",
    "CreateAssemblyGroundedJointReceipt",
    "apply_create_assembly_grounded_joint",
    "build_create_assembly_grounded_joint_request",
    "read_create_assembly_grounded_joint_result",
    "rpc_create_assembly_grounded_joint",
    "run_create_assembly_grounded_joint",
    "TYPED_RPC_HANDLER",
]
