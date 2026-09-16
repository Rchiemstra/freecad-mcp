"""Typed ``create_assembly`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.create_assembly_contract import (
    DocumentName,
    AssemblyName,
    CreateAssemblyCollaborators,
    CreateAssemblyFailure,
    CreateAssemblyRequest,
    CreateAssemblyResult,
    MutationDocument,
    MutationObject,
    MutationReadDocument,
    make_create_assembly_failure,
    make_create_assembly_success,
    make_create_assembly_uncertain,
)
from .typed_runtime import as_float, as_int, as_str
from . import assembly_actions
from .create_assembly_mutation import CreateAssemblyError, run_create_assembly_native_mutation


@dataclass(frozen=True, slots=True)
class CreateAssemblyReceipt:
    payload: dict[str, object]
    obj: MutationObject | None


@dataclass(frozen=True, slots=True)
class CreateAssemblyInspection:
    payload: dict[str, object]


def _failure(error: CreateAssemblyError, *, retry_safe: bool = True) -> CreateAssemblyFailure:
    return make_create_assembly_failure(error.code, str(error), retry_safe=retry_safe)


def build_create_assembly_request(
    doc_name: object, assembly_name: object, create_joint_group: object, recompute: object, if_exists: object
) -> CreateAssemblyRequest | CreateAssemblyFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(CreateAssemblyError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if assembly_name is None:
        assembly_name_value = "Assembly"
    elif not isinstance(assembly_name, str) or not assembly_name.strip():
        return _failure(CreateAssemblyError("INVALID_ARGUMENT", "assembly_name must be a nonempty string"))
    else:
        assembly_name_value = assembly_name
    if create_joint_group is None:
        create_joint_group_value = True
    elif not isinstance(create_joint_group, bool):
        return _failure(CreateAssemblyError("INVALID_ARGUMENT", "create_joint_group must be a boolean"))
    else:
        create_joint_group_value = create_joint_group
    if recompute is None:
        recompute_value = False
    elif not isinstance(recompute, bool):
        return _failure(CreateAssemblyError("INVALID_ARGUMENT", "recompute must be a boolean"))
    else:
        recompute_value = recompute
    if if_exists is None:
        if_exists_value = "error"
    elif not isinstance(if_exists, str) or not if_exists.strip():
        return _failure(CreateAssemblyError("INVALID_ARGUMENT", "if_exists must be a nonempty string"))
    else:
        if_exists_value = if_exists
    request = CreateAssemblyRequest(
        doc_name=DocumentName(doc_name),
        assembly_name=AssemblyName(assembly_name_value),
        create_joint_group=create_joint_group_value,
        recompute=recompute_value,
        if_exists=if_exists_value
    )
    if request.if_exists not in {"error", "skip", "replace"}:
        return _failure(CreateAssemblyError("INVALID_ARGUMENT", "if_exists must be error, skip, or replace"))
    return request


@dataclass(slots=True)
class _CreateAssemblyExecution:
    collaborators: CreateAssemblyCollaborators
    request: CreateAssemblyRequest
    created: CreateAssemblyReceipt | None = None
    inspected: CreateAssemblyInspection | None = None

    def apply(self, doc: MutationDocument) -> None:
        self.created = apply_create_assembly(doc, self.request)

    def inspect(self, doc: MutationReadDocument) -> None:
        if self.created is None:
            raise CreateAssemblyError(
                "INVALID_CREATE_ASSEMBLY_RESULT",
                "create_assembly did not return an identity receipt",
            )
        self.inspected = read_create_assembly_result(doc, self.created, self.request)

    def run(self) -> CreateAssemblyResult:
        result = run_create_assembly_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_create_assembly_uncertain(
                "CREATE_ASSEMBLY_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected create_assembly result",
                committed=True,
            )
        payload = self.inspected.payload
        return make_create_assembly_success(
            assembly=AssemblyName(as_str(payload["assembly"])), label=as_str(payload["label"]), type=as_str(payload["type"]), joint_group=(as_str(payload["joint_group"]) if payload.get("joint_group") is not None else None)
        )


def apply_create_assembly(doc: MutationDocument, request: CreateAssemblyRequest) -> CreateAssemblyReceipt:
    """Apply create_assembly without recomputing or managing a transaction."""

    payload = assembly_actions.create_assembly(doc, assembly_name=request.assembly_name, create_joint_group=request.create_joint_group, if_exists=request.if_exists)
    target = payload.get("assembly")
    found = doc.getObject(str(target)) if isinstance(target, str) else None
    return CreateAssemblyReceipt(payload=dict(payload), obj=found)



def read_create_assembly_result(
    doc: MutationReadDocument, receipt: CreateAssemblyReceipt, request: CreateAssemblyRequest
) -> CreateAssemblyInspection:
    key = "assembly"
    name = receipt.payload.get(key)
    if not isinstance(name, str) or not name.strip():
        raise CreateAssemblyError("INVALID_CREATE_ASSEMBLY_RESULT", "missing created identity")
    obj = doc.getObject(name)
    if obj is None:
        raise CreateAssemblyError("CREATED_OBJECT_MISSING", f"Created object is missing: {name!r}")
    if receipt.obj is not None and obj is not receipt.obj:
        raise CreateAssemblyError("CREATED_OBJECT_REPLACED", f"Created object was replaced: {name!r}")

    if obj is not None and not (
        (callable(getattr(obj, "isDerivedFrom", None)) and obj.isDerivedFrom("Assembly::AssemblyObject"))
        or obj.TypeId == "Assembly::AssemblyObject"
    ):
        raise CreateAssemblyError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Created object is not Assembly::AssemblyObject: {obj.Name!r}",
        )

    payload = dict(receipt.payload)
    if hasattr(obj, "Label") and "label" in payload:
        payload["label"] = str(obj.Label)
    return CreateAssemblyInspection(payload=payload)



def run_create_assembly(
    collaborators: CreateAssemblyCollaborators,
    doc_name: str, assembly_name: str = "Assembly", create_joint_group: bool = True, recompute: bool = False, if_exists: str = "error",
) -> CreateAssemblyResult:
    """Run create_assembly through apply, recompute, inspection, and commit."""

    request = build_create_assembly_request(doc_name, assembly_name, create_joint_group, recompute, if_exists)
    if isinstance(request, dict):
        return request
    return _CreateAssemblyExecution(collaborators, request).run()


class _CreateAssemblyRpcFacade(Protocol):
    _cad_collaborators: CreateAssemblyCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_create_assembly(
    self: _CreateAssemblyRpcFacade,
    doc_name: str, assembly_name: str = "Assembly", create_joint_group: bool = True, recompute: bool = False, if_exists: str = "error",
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_create_assembly(collaborators, doc_name, assembly_name, create_joint_group, recompute, if_exists)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("create_assembly", rpc_create_assembly)


__all__ = [
    "CreateAssemblyCollaborators",
    "CreateAssemblyError",
    "CreateAssemblyInspection",
    "CreateAssemblyReceipt",
    "apply_create_assembly",
    "build_create_assembly_request",
    "read_create_assembly_result",
    "rpc_create_assembly",
    "run_create_assembly",
    "TYPED_RPC_HANDLER",
]
