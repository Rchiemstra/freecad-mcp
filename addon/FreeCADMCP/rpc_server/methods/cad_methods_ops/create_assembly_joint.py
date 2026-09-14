"""Typed ``create_assembly_joint`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.create_assembly_joint_contract import (
    DocumentName,
    AssemblyName,
    CreateAssemblyJointCollaborators,
    CreateAssemblyJointFailure,
    CreateAssemblyJointRequest,
    CreateAssemblyJointResult,
    MutationDocument,
    MutationObject,
    MutationReadDocument,
    make_create_assembly_joint_failure,
    make_create_assembly_joint_success,
    make_create_assembly_joint_uncertain,
)
from .typed_runtime import as_float, as_int, as_str
from . import assembly_actions
from .create_assembly_joint_mutation import CreateAssemblyJointError, run_create_assembly_joint_native_mutation


@dataclass(frozen=True, slots=True)
class CreateAssemblyJointReceipt:
    payload: dict[str, object]
    obj: MutationObject | None


@dataclass(frozen=True, slots=True)
class CreateAssemblyJointInspection:
    payload: dict[str, object]


def _failure(error: CreateAssemblyJointError, *, retry_safe: bool = True) -> CreateAssemblyJointFailure:
    return make_create_assembly_joint_failure(error.code, str(error), retry_safe=retry_safe)


def build_create_assembly_joint_request(
    doc_name: object, assembly_name: object, joint_type: object, ref1_component: object, ref2_component: object, ref1_element: object, ref2_element: object, ref1_vertex: object, ref2_vertex: object, label: object, solve: object, presolve: object, recompute: object, properties: object
) -> CreateAssemblyJointRequest | CreateAssemblyJointFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(CreateAssemblyJointError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(assembly_name, str) or not assembly_name.strip():
        return _failure(CreateAssemblyJointError("INVALID_ARGUMENT", "assembly_name must be a nonempty string"))
    if not isinstance(joint_type, str) or not joint_type.strip():
        return _failure(CreateAssemblyJointError("INVALID_ARGUMENT", "joint_type must be a nonempty string"))
    if not isinstance(ref1_component, str) or not ref1_component.strip():
        return _failure(CreateAssemblyJointError("INVALID_ARGUMENT", "ref1_component must be a nonempty string"))
    if not isinstance(ref2_component, str) or not ref2_component.strip():
        return _failure(CreateAssemblyJointError("INVALID_ARGUMENT", "ref2_component must be a nonempty string"))
    if ref1_element is None:
        ref1_element_value: str = ""
    elif not isinstance(ref1_element, str):
        return _failure(CreateAssemblyJointError("INVALID_ARGUMENT", "ref1_element must be a string or null"))
    else:
        ref1_element_value = ref1_element
    if ref2_element is None:
        ref2_element_value: str = ""
    elif not isinstance(ref2_element, str):
        return _failure(CreateAssemblyJointError("INVALID_ARGUMENT", "ref2_element must be a string or null"))
    else:
        ref2_element_value = ref2_element
    if ref1_vertex is None:
        ref1_vertex_value: str | None = None
    elif not isinstance(ref1_vertex, str):
        return _failure(CreateAssemblyJointError("INVALID_ARGUMENT", "ref1_vertex must be a string or null"))
    else:
        ref1_vertex_value = ref1_vertex
    if ref2_vertex is None:
        ref2_vertex_value: str | None = None
    elif not isinstance(ref2_vertex, str):
        return _failure(CreateAssemblyJointError("INVALID_ARGUMENT", "ref2_vertex must be a string or null"))
    else:
        ref2_vertex_value = ref2_vertex
    if label is None:
        label_value: str | None = None
    elif not isinstance(label, str):
        return _failure(CreateAssemblyJointError("INVALID_ARGUMENT", "label must be a string or null"))
    else:
        label_value = label
    if solve is None:
        solve_value = True
    elif not isinstance(solve, bool):
        return _failure(CreateAssemblyJointError("INVALID_ARGUMENT", "solve must be a boolean"))
    else:
        solve_value = solve
    if presolve is None:
        presolve_value = True
    elif not isinstance(presolve, bool):
        return _failure(CreateAssemblyJointError("INVALID_ARGUMENT", "presolve must be a boolean"))
    else:
        presolve_value = presolve
    if recompute is None:
        recompute_value = True
    elif not isinstance(recompute, bool):
        return _failure(CreateAssemblyJointError("INVALID_ARGUMENT", "recompute must be a boolean"))
    else:
        recompute_value = recompute
    if properties is None:
        properties_value: dict[str, object] | None = None
    elif not isinstance(properties, dict) or any(not isinstance(key, str) for key in properties):
        return _failure(CreateAssemblyJointError("INVALID_ARGUMENT", "properties must be an object"))
    else:
        properties_value = {str(key): value for key, value in properties.items()}
    request = CreateAssemblyJointRequest(
        doc_name=DocumentName(doc_name),
        assembly_name=AssemblyName(assembly_name),
        joint_type=joint_type,
        ref1_component=ref1_component,
        ref2_component=ref2_component,
        ref1_element=ref1_element_value,
        ref2_element=ref2_element_value,
        ref1_vertex=ref1_vertex_value,
        ref2_vertex=ref2_vertex_value,
        label=label_value,
        solve=solve_value,
        presolve=presolve_value,
        recompute=recompute_value,
        properties=properties_value
    )
    return request


@dataclass(slots=True)
class _CreateAssemblyJointExecution:
    collaborators: CreateAssemblyJointCollaborators
    request: CreateAssemblyJointRequest
    created: CreateAssemblyJointReceipt | None = None
    inspected: CreateAssemblyJointInspection | None = None

    def apply(self, doc: MutationDocument) -> None:
        self.created = apply_create_assembly_joint(doc, self.request)

    def inspect(self, doc: MutationReadDocument) -> None:
        if self.created is None:
            raise CreateAssemblyJointError(
                "INVALID_CREATE_ASSEMBLY_JOINT_RESULT",
                "create_assembly_joint did not return an identity receipt",
            )
        self.inspected = read_create_assembly_joint_result(doc, self.created, self.request)

    def run(self) -> CreateAssemblyJointResult:
        result = run_create_assembly_joint_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_create_assembly_joint_uncertain(
                "CREATE_ASSEMBLY_JOINT_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected create_assembly_joint result",
                committed=True,
            )
        payload = self.inspected.payload
        return make_create_assembly_joint_success(
            joint=as_str(payload["joint"]), label=as_str(payload["label"]), joint_type=as_str(payload["joint_type"]), assembly=as_str(payload["assembly"])
        )


def apply_create_assembly_joint(doc: MutationDocument, request: CreateAssemblyJointRequest) -> CreateAssemblyJointReceipt:
    """Apply create_assembly_joint without recomputing or managing a transaction."""

    payload = assembly_actions.create_joint(doc, assembly_name=request.assembly_name, joint_type=request.joint_type, ref1_component=request.ref1_component, ref2_component=request.ref2_component, ref1_element=request.ref1_element, ref2_element=request.ref2_element, ref1_vertex=request.ref1_vertex, ref2_vertex=request.ref2_vertex, label=request.label, solve=request.solve, presolve=request.presolve, properties=request.properties or {})
    target = payload.get("joint")
    found = doc.getObject(str(target)) if isinstance(target, str) else None
    return CreateAssemblyJointReceipt(payload=dict(payload), obj=found)



def read_create_assembly_joint_result(
    doc: MutationReadDocument, receipt: CreateAssemblyJointReceipt, request: CreateAssemblyJointRequest
) -> CreateAssemblyJointInspection:
    key = "joint"
    name = receipt.payload.get(key)
    if not isinstance(name, str) or not name.strip():
        raise CreateAssemblyJointError("INVALID_CREATE_ASSEMBLY_JOINT_RESULT", "missing created identity")
    obj = doc.getObject(name)
    if obj is None:
        raise CreateAssemblyJointError("CREATED_OBJECT_MISSING", f"Created object is missing: {name!r}")
    if receipt.obj is not None and obj is not receipt.obj:
        raise CreateAssemblyJointError("CREATED_OBJECT_REPLACED", f"Created object was replaced: {name!r}")

    payload = dict(receipt.payload)
    if hasattr(obj, "Label") and "label" in payload:
        payload["label"] = str(obj.Label)
    return CreateAssemblyJointInspection(payload=payload)



def run_create_assembly_joint(
    collaborators: CreateAssemblyJointCollaborators,
    doc_name: str, assembly_name: str, joint_type: str, ref1_component: str, ref2_component: str, ref1_element: str = "", ref2_element: str = "", ref1_vertex: str | None = None, ref2_vertex: str | None = None, label: str | None = None, solve: bool = True, presolve: bool = True, recompute: bool = True, properties: dict[str, object] | None = None,
) -> CreateAssemblyJointResult:
    """Run create_assembly_joint through apply, recompute, inspection, and commit."""

    request = build_create_assembly_joint_request(doc_name, assembly_name, joint_type, ref1_component, ref2_component, ref1_element, ref2_element, ref1_vertex, ref2_vertex, label, solve, presolve, recompute, properties)
    if isinstance(request, dict):
        return request
    return _CreateAssemblyJointExecution(collaborators, request).run()


class _CreateAssemblyJointRpcFacade(Protocol):
    _cad_collaborators: CreateAssemblyJointCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_create_assembly_joint(
    self: _CreateAssemblyJointRpcFacade,
    doc_name: str, assembly_name: str, joint_type: str, ref1_component: str, ref2_component: str, ref1_element: str = "", ref2_element: str = "", ref1_vertex: str | None = None, ref2_vertex: str | None = None, label: str | None = None, solve: bool = True, presolve: bool = True, recompute: bool = True, properties: dict[str, object] | None = None,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_create_assembly_joint(collaborators, doc_name, assembly_name, joint_type, ref1_component, ref2_component, ref1_element, ref2_element, ref1_vertex, ref2_vertex, label, solve, presolve, recompute, properties)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("create_assembly_joint", rpc_create_assembly_joint)


__all__ = [
    "CreateAssemblyJointCollaborators",
    "CreateAssemblyJointError",
    "CreateAssemblyJointInspection",
    "CreateAssemblyJointReceipt",
    "apply_create_assembly_joint",
    "build_create_assembly_joint_request",
    "read_create_assembly_joint_result",
    "rpc_create_assembly_joint",
    "run_create_assembly_joint",
    "TYPED_RPC_HANDLER",
]
