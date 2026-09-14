"""Typed ``export_step`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.export_step_contract import (
    DocumentName,
    ExportStepCollaborators,
    ExportStepFailure,
    ExportStepRequest,
    ExportStepResult,
    MutationDocument,
    MutationObject,
    MutationReadDocument,
    make_export_step_failure,
    make_export_step_success,
    make_export_step_uncertain,
)
from .typed_runtime import as_float, as_int, as_str
from . import measure_io_actions
from .export_step_mutation import ExportStepError, run_export_step_native_mutation


@dataclass(frozen=True, slots=True)
class ExportStepReceipt:
    payload: dict[str, object]
    obj: MutationObject | None


@dataclass(frozen=True, slots=True)
class ExportStepInspection:
    payload: dict[str, object]


def _failure(error: ExportStepError, *, retry_safe: bool = True) -> ExportStepFailure:
    return make_export_step_failure(error.code, str(error), retry_safe=retry_safe)


def build_export_step_request(
    doc_name: object, file_path: object, obj_names: object
) -> ExportStepRequest | ExportStepFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(ExportStepError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(file_path, str) or not file_path.strip():
        return _failure(ExportStepError("INVALID_ARGUMENT", "file_path must be a nonempty string"))
    if obj_names is None:
        obj_names_value: list[str] | None = None
    elif not isinstance(obj_names, list) or any(not isinstance(item, str) for item in obj_names):
        return _failure(ExportStepError("INVALID_ARGUMENT", "obj_names must be a list of strings"))
    else:
        obj_names_value = obj_names
    request = ExportStepRequest(
        doc_name=DocumentName(doc_name),
        file_path=file_path,
        obj_names=obj_names_value
    )
    return request


@dataclass(slots=True)
class _ExportStepExecution:
    collaborators: ExportStepCollaborators
    request: ExportStepRequest
    created: ExportStepReceipt | None = None
    inspected: ExportStepInspection | None = None

    def apply(self, doc: MutationDocument) -> None:
        self.created = apply_export_step(doc, self.request)

    def inspect(self, doc: MutationReadDocument) -> None:
        if self.created is None:
            raise ExportStepError(
                "INVALID_EXPORT_STEP_RESULT",
                "export_step did not return an identity receipt",
            )
        self.inspected = read_export_step_result(doc, self.created, self.request)

    def run(self) -> ExportStepResult:
        result = run_export_step_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_export_step_uncertain(
                "EXPORT_STEP_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected export_step result",
                committed=True,
            )
        payload = self.inspected.payload
        return make_export_step_success(
            path=as_str(payload["path"]), exported=as_int(payload["exported"])
        )


def apply_export_step(doc: MutationDocument, request: ExportStepRequest) -> ExportStepReceipt:
    """Apply export_step without recomputing or managing a transaction."""

    payload = measure_io_actions.export_step(doc, request.file_path, request.obj_names)
    return ExportStepReceipt(payload=payload, obj=None)



def read_export_step_result(
    doc: MutationReadDocument, receipt: ExportStepReceipt, request: ExportStepRequest
) -> ExportStepInspection:
    path = receipt.payload.get("path")
    if not isinstance(path, str) or not path.strip():
        raise ExportStepError("INVALID_EXPORT_STEP_RESULT", "missing export path")
    return ExportStepInspection(payload=dict(receipt.payload))



def run_export_step(
    collaborators: ExportStepCollaborators,
    doc_name: str, file_path: str, obj_names: list[str] | None = None,
) -> ExportStepResult:
    """Run export_step through apply, recompute, inspection, and commit."""

    request = build_export_step_request(doc_name, file_path, obj_names)
    if isinstance(request, dict):
        return request
    return _ExportStepExecution(collaborators, request).run()


class _ExportStepRpcFacade(Protocol):
    _cad_collaborators: ExportStepCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_export_step(
    self: _ExportStepRpcFacade,
    doc_name: str, file_path: str, obj_names: list[str] | None = None,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_export_step(collaborators, doc_name, file_path, obj_names)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("export_step", rpc_export_step)


__all__ = [
    "ExportStepCollaborators",
    "ExportStepError",
    "ExportStepInspection",
    "ExportStepReceipt",
    "apply_export_step",
    "build_export_step_request",
    "read_export_step_result",
    "rpc_export_step",
    "run_export_step",
    "TYPED_RPC_HANDLER",
]
