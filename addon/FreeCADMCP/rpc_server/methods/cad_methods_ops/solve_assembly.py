"""Typed ``solve_assembly`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

try:
    from ...._shared.protocol.solve_assembly_contract import (
        DocumentName,
        AssemblyName,
        SolveAssemblyCollaborators,
        SolveAssemblyFailure,
        SolveAssemblyRequest,
        SolveAssemblyResult,
        MutationDocument,
        MutationObject,
        MutationReadDocument,
        make_solve_assembly_failure,
        make_solve_assembly_success,
        make_solve_assembly_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.solve_assembly_contract import (
        DocumentName,
        AssemblyName,
        SolveAssemblyCollaborators,
        SolveAssemblyFailure,
        SolveAssemblyRequest,
        SolveAssemblyResult,
        MutationDocument,
        MutationObject,
        MutationReadDocument,
        make_solve_assembly_failure,
        make_solve_assembly_success,
        make_solve_assembly_uncertain,
    )
from .typed_runtime import as_float, as_int, as_str
from . import assembly_actions
from .solve_assembly_mutation import SolveAssemblyError, run_solve_assembly_native_mutation


@dataclass(frozen=True, slots=True)
class SolveAssemblyReceipt:
    payload: dict[str, object]
    obj: MutationObject | None


@dataclass(frozen=True, slots=True)
class SolveAssemblyInspection:
    payload: dict[str, object]


def _failure(error: SolveAssemblyError, *, retry_safe: bool = True) -> SolveAssemblyFailure:
    return make_solve_assembly_failure(error.code, str(error), retry_safe=retry_safe)


def build_solve_assembly_request(
    doc_name: object, assembly_name: object
) -> SolveAssemblyRequest | SolveAssemblyFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(SolveAssemblyError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(assembly_name, str) or not assembly_name.strip():
        return _failure(SolveAssemblyError("INVALID_ARGUMENT", "assembly_name must be a nonempty string"))
    request = SolveAssemblyRequest(
        doc_name=DocumentName(doc_name),
        assembly_name=AssemblyName(assembly_name)
    )
    return request


@dataclass(slots=True)
class _SolveAssemblyExecution:
    collaborators: SolveAssemblyCollaborators
    request: SolveAssemblyRequest
    created: SolveAssemblyReceipt | None = None
    inspected: SolveAssemblyInspection | None = None

    def apply(self, doc: MutationDocument) -> None:
        self.created = apply_solve_assembly(doc, self.request)

    def inspect(self, doc: MutationReadDocument) -> None:
        if self.created is None:
            raise SolveAssemblyError(
                "INVALID_SOLVE_ASSEMBLY_RESULT",
                "solve_assembly did not return an identity receipt",
            )
        self.inspected = read_solve_assembly_result(doc, self.created, self.request)

    def run(self) -> SolveAssemblyResult:
        result = run_solve_assembly_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_solve_assembly_uncertain(
                "SOLVE_ASSEMBLY_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected solve_assembly result",
                committed=True,
            )
        payload = self.inspected.payload
        return make_solve_assembly_success(
            assembly=as_str(payload["assembly"]), method=as_str(payload["method"]), status=(as_str(payload["status"]) if payload.get("status") is not None else None)
        )


def apply_solve_assembly(doc: MutationDocument, request: SolveAssemblyRequest) -> SolveAssemblyReceipt:
    """Apply solve_assembly without recomputing or managing a transaction."""

    payload = assembly_actions.solve_assembly(doc, request.assembly_name)
    typed_payload: dict[str, object] = {str(key): value for key, value in payload.items()}
    assembly = typed_payload.get("assembly")
    return SolveAssemblyReceipt(
        payload=typed_payload,
        obj=doc.getObject(as_str(assembly)) if assembly is not None else None,
    )



def read_solve_assembly_result(
    doc: MutationReadDocument, receipt: SolveAssemblyReceipt, request: SolveAssemblyRequest
) -> SolveAssemblyInspection:
    key = "assembly"
    name = receipt.payload.get(key)
    if not isinstance(name, str) or not name.strip():
        raise SolveAssemblyError("INVALID_SOLVE_ASSEMBLY_RESULT", "missing created identity")
    obj = doc.getObject(name)
    if obj is None:
        raise SolveAssemblyError("CREATED_OBJECT_MISSING", f"Created object is missing: {name!r}")
    if receipt.obj is not None and obj is not receipt.obj:
        raise SolveAssemblyError("CREATED_OBJECT_REPLACED", f"Created object was replaced: {name!r}")

    if obj is not None and not (
        (callable(getattr(obj, "isDerivedFrom", None)) and obj.isDerivedFrom("Assembly::AssemblyObject"))
        or obj.TypeId == "Assembly::AssemblyObject"
    ):
        raise SolveAssemblyError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Created object is not Assembly::AssemblyObject: {obj.Name!r}",
        )

    payload = dict(receipt.payload)
    if hasattr(obj, "Label") and "label" in payload:
        payload["label"] = str(obj.Label)
    return SolveAssemblyInspection(payload=payload)



def run_solve_assembly(
    collaborators: SolveAssemblyCollaborators,
    doc_name: str, assembly_name: str,
) -> SolveAssemblyResult:
    """Run solve_assembly through apply, recompute, inspection, and commit."""

    request = build_solve_assembly_request(doc_name, assembly_name)
    if isinstance(request, dict):
        return request
    return _SolveAssemblyExecution(collaborators, request).run()


class _SolveAssemblyRpcFacade(Protocol):
    _cad_collaborators: SolveAssemblyCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_solve_assembly(
    self: _SolveAssemblyRpcFacade,
    doc_name: str, assembly_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_solve_assembly(collaborators, doc_name, assembly_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("solve_assembly", rpc_solve_assembly)


__all__ = [
    "SolveAssemblyCollaborators",
    "SolveAssemblyError",
    "SolveAssemblyInspection",
    "SolveAssemblyReceipt",
    "apply_solve_assembly",
    "build_solve_assembly_request",
    "read_solve_assembly_result",
    "rpc_solve_assembly",
    "run_solve_assembly",
    "TYPED_RPC_HANDLER",
]
