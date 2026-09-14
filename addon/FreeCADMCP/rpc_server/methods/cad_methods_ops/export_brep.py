"""Typed ``export_brep`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.export_brep_contract import (
    ObjectName,
    DocumentName,
    ExportBrepCollaborators,
    ExportBrepFailure,
    ExportBrepRequest,
    ExportBrepResult,
    MutationDocument,
    MutationObject,
    MutationReadDocument,
    make_export_brep_failure,
    make_export_brep_success,
    make_export_brep_uncertain,
)
from .typed_runtime import as_float, as_int, as_str
from . import measure_io_actions
from .export_brep_mutation import ExportBrepError, run_export_brep_native_mutation


@dataclass(frozen=True, slots=True)
class ExportBrepReceipt:
    payload: dict[str, object]
    obj: MutationObject | None


@dataclass(frozen=True, slots=True)
class ExportBrepInspection:
    payload: dict[str, object]


def _failure(error: ExportBrepError, *, retry_safe: bool = True) -> ExportBrepFailure:
    return make_export_brep_failure(error.code, str(error), retry_safe=retry_safe)


def build_export_brep_request(
    doc_name: object, obj_name: object, file_path: object
) -> ExportBrepRequest | ExportBrepFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(ExportBrepError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(obj_name, str) or not obj_name.strip():
        return _failure(ExportBrepError("INVALID_ARGUMENT", "obj_name must be a nonempty string"))
    if not isinstance(file_path, str) or not file_path.strip():
        return _failure(ExportBrepError("INVALID_ARGUMENT", "file_path must be a nonempty string"))
    request = ExportBrepRequest(
        doc_name=DocumentName(doc_name),
        obj_name=ObjectName(obj_name),
        file_path=file_path
    )
    return request


@dataclass(slots=True)
class _ExportBrepExecution:
    collaborators: ExportBrepCollaborators
    request: ExportBrepRequest
    created: ExportBrepReceipt | None = None
    inspected: ExportBrepInspection | None = None

    def apply(self, doc: MutationDocument) -> None:
        self.created = apply_export_brep(doc, self.request)

    def inspect(self, doc: MutationReadDocument) -> None:
        if self.created is None:
            raise ExportBrepError(
                "INVALID_EXPORT_BREP_RESULT",
                "export_brep did not return an identity receipt",
            )
        self.inspected = read_export_brep_result(doc, self.created, self.request)

    def run(self) -> ExportBrepResult:
        result = run_export_brep_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_export_brep_uncertain(
                "EXPORT_BREP_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected export_brep result",
                committed=True,
            )
        payload = self.inspected.payload
        return make_export_brep_success(
            path=as_str(payload["path"]), exported=bool(payload["exported"]), object=as_str(payload["object"])
        )


def apply_export_brep(doc: MutationDocument, request: ExportBrepRequest) -> ExportBrepReceipt:
    """Apply export_brep without recomputing or managing a transaction."""

    payload = measure_io_actions.export_brep(doc, request.obj_name, request.file_path)
    target = payload.get("object")
    found = doc.getObject(str(target)) if isinstance(target, str) else None
    return ExportBrepReceipt(payload=dict(payload), obj=found)



def read_export_brep_result(
    doc: MutationReadDocument, receipt: ExportBrepReceipt, request: ExportBrepRequest
) -> ExportBrepInspection:
    key = "object"
    name = receipt.payload.get(key)
    if not isinstance(name, str) or not name.strip():
        raise ExportBrepError("INVALID_EXPORT_BREP_RESULT", "missing created identity")
    obj = doc.getObject(name)
    if obj is None:
        raise ExportBrepError("CREATED_OBJECT_MISSING", f"Created object is missing: {name!r}")
    if receipt.obj is not None and obj is not receipt.obj:
        raise ExportBrepError("CREATED_OBJECT_REPLACED", f"Created object was replaced: {name!r}")

    payload = dict(receipt.payload)
    if hasattr(obj, "Label") and "label" in payload:
        payload["label"] = str(obj.Label)
    return ExportBrepInspection(payload=payload)



def run_export_brep(
    collaborators: ExportBrepCollaborators,
    doc_name: str, obj_name: str, file_path: str,
) -> ExportBrepResult:
    """Run export_brep through apply, recompute, inspection, and commit."""

    request = build_export_brep_request(doc_name, obj_name, file_path)
    if isinstance(request, dict):
        return request
    return _ExportBrepExecution(collaborators, request).run()


class _ExportBrepRpcFacade(Protocol):
    _cad_collaborators: ExportBrepCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_export_brep(
    self: _ExportBrepRpcFacade,
    doc_name: str, obj_name: str, file_path: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_export_brep(collaborators, doc_name, obj_name, file_path)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("export_brep", rpc_export_brep)


__all__ = [
    "ExportBrepCollaborators",
    "ExportBrepError",
    "ExportBrepInspection",
    "ExportBrepReceipt",
    "apply_export_brep",
    "build_export_brep_request",
    "read_export_brep_result",
    "rpc_export_brep",
    "run_export_brep",
    "TYPED_RPC_HANDLER",
]
