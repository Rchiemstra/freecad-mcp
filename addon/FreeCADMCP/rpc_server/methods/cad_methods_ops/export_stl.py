"""Typed ``export_stl`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.export_stl_contract import (
    DocumentName,
    ExportStlCollaborators,
    ExportStlFailure,
    ExportStlRequest,
    ExportStlResult,
    MutationDocument,
    MutationObject,
    MutationReadDocument,
    make_export_stl_failure,
    make_export_stl_success,
    make_export_stl_uncertain,
)
from .typed_runtime import as_float, as_int, as_str
from . import measure_io_actions
from .export_stl_mutation import ExportStlError, run_export_stl_native_mutation


@dataclass(frozen=True, slots=True)
class ExportStlReceipt:
    payload: dict[str, object]
    obj: MutationObject | None


@dataclass(frozen=True, slots=True)
class ExportStlInspection:
    payload: dict[str, object]


def _failure(error: ExportStlError, *, retry_safe: bool = True) -> ExportStlFailure:
    return make_export_stl_failure(error.code, str(error), retry_safe=retry_safe)


def build_export_stl_request(
    doc_name: object, file_path: object, obj_names: object, mesh_deviation: object
) -> ExportStlRequest | ExportStlFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(ExportStlError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(file_path, str) or not file_path.strip():
        return _failure(ExportStlError("INVALID_ARGUMENT", "file_path must be a nonempty string"))
    if obj_names is None:
        obj_names_value: list[str] | None = None
    elif not isinstance(obj_names, list) or any(not isinstance(item, str) for item in obj_names):
        return _failure(ExportStlError("INVALID_ARGUMENT", "obj_names must be a list of strings"))
    else:
        obj_names_value = obj_names
    if mesh_deviation is None:
        mesh_deviation_value = float(0.1)
    elif isinstance(mesh_deviation, bool) or not isinstance(mesh_deviation, (int, float)):
        return _failure(ExportStlError("INVALID_ARGUMENT", "mesh_deviation must be a number"))
    else:
        mesh_deviation_value = float(mesh_deviation)
    request = ExportStlRequest(
        doc_name=DocumentName(doc_name),
        file_path=file_path,
        obj_names=obj_names_value,
        mesh_deviation=mesh_deviation_value
    )
    return request


@dataclass(slots=True)
class _ExportStlExecution:
    collaborators: ExportStlCollaborators
    request: ExportStlRequest
    created: ExportStlReceipt | None = None
    inspected: ExportStlInspection | None = None

    def apply(self, doc: MutationDocument) -> None:
        self.created = apply_export_stl(doc, self.request)

    def inspect(self, doc: MutationReadDocument) -> None:
        if self.created is None:
            raise ExportStlError(
                "INVALID_EXPORT_STL_RESULT",
                "export_stl did not return an identity receipt",
            )
        self.inspected = read_export_stl_result(doc, self.created, self.request)

    def run(self) -> ExportStlResult:
        result = run_export_stl_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_export_stl_uncertain(
                "EXPORT_STL_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected export_stl result",
                committed=True,
            )
        payload = self.inspected.payload
        return make_export_stl_success(
            path=as_str(payload["path"]), exported=as_int(payload["exported"]), faces=as_int(payload["faces"])
        )


def apply_export_stl(doc: MutationDocument, request: ExportStlRequest) -> ExportStlReceipt:
    """Apply export_stl without recomputing or managing a transaction."""

    payload = measure_io_actions.export_stl(doc, request.file_path, request.obj_names, request.mesh_deviation)
    return ExportStlReceipt(payload=payload, obj=None)



def read_export_stl_result(
    doc: MutationReadDocument, receipt: ExportStlReceipt, request: ExportStlRequest
) -> ExportStlInspection:
    path = receipt.payload.get("path")
    if not isinstance(path, str) or not path.strip():
        raise ExportStlError("INVALID_EXPORT_STL_RESULT", "missing export path")
    return ExportStlInspection(payload=dict(receipt.payload))



def run_export_stl(
    collaborators: ExportStlCollaborators,
    doc_name: str, file_path: str, obj_names: list[str] | None = None, mesh_deviation: float = 0.1,
) -> ExportStlResult:
    """Run export_stl through apply, recompute, inspection, and commit."""

    request = build_export_stl_request(doc_name, file_path, obj_names, mesh_deviation)
    if isinstance(request, dict):
        return request
    return _ExportStlExecution(collaborators, request).run()


class _ExportStlRpcFacade(Protocol):
    _cad_collaborators: ExportStlCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_export_stl(
    self: _ExportStlRpcFacade,
    doc_name: str, file_path: str, obj_names: list[str] | None = None, mesh_deviation: float = 0.1,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_export_stl(collaborators, doc_name, file_path, obj_names, mesh_deviation)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("export_stl", rpc_export_stl)


__all__ = [
    "ExportStlCollaborators",
    "ExportStlError",
    "ExportStlInspection",
    "ExportStlReceipt",
    "apply_export_stl",
    "build_export_stl_request",
    "read_export_stl_result",
    "rpc_export_stl",
    "run_export_stl",
    "TYPED_RPC_HANDLER",
]
