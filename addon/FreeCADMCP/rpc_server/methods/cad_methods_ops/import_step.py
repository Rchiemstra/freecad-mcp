"""Typed ``import_step`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.import_step_contract import (
    DocumentName,
    ImportStepCollaborators,
    ImportStepFailure,
    ImportStepRequest,
    ImportStepResult,
    MutationDocument,
    MutationObject,
    MutationReadDocument,
    make_import_step_failure,
    make_import_step_success,
    make_import_step_uncertain,
)
from .typed_runtime import as_float, as_int, as_str
from . import measure_io_actions
from .import_step_mutation import ImportStepError, run_import_step_native_mutation


@dataclass(frozen=True, slots=True)
class ImportStepReceipt:
    payload: dict[str, object]
    obj: MutationObject | None


@dataclass(frozen=True, slots=True)
class ImportStepInspection:
    payload: dict[str, object]


def _failure(error: ImportStepError, *, retry_safe: bool = True) -> ImportStepFailure:
    return make_import_step_failure(error.code, str(error), retry_safe=retry_safe)


def build_import_step_request(
    doc_name: object, file_path: object
) -> ImportStepRequest | ImportStepFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(ImportStepError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(file_path, str) or not file_path.strip():
        return _failure(ImportStepError("INVALID_ARGUMENT", "file_path must be a nonempty string"))
    request = ImportStepRequest(
        doc_name=DocumentName(doc_name),
        file_path=file_path
    )
    return request


@dataclass(slots=True)
class _ImportStepExecution:
    collaborators: ImportStepCollaborators
    request: ImportStepRequest
    created: ImportStepReceipt | None = None
    inspected: ImportStepInspection | None = None

    def apply(self, doc: MutationDocument) -> None:
        self.created = apply_import_step(doc, self.request)

    def inspect(self, doc: MutationReadDocument) -> None:
        if self.created is None:
            raise ImportStepError(
                "INVALID_IMPORT_STEP_RESULT",
                "import_step did not return an identity receipt",
            )
        self.inspected = read_import_step_result(doc, self.created, self.request)

    def run(self) -> ImportStepResult:
        result = run_import_step_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_import_step_uncertain(
                "IMPORT_STEP_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected import_step result",
                committed=True,
            )
        payload = self.inspected.payload
        return make_import_step_success(
            path=as_str(payload["path"]), imported=bool(payload["imported"])
        )


def apply_import_step(doc: MutationDocument, request: ImportStepRequest) -> ImportStepReceipt:
    """Apply import_step without recomputing or managing a transaction."""

    payload = measure_io_actions.import_step(doc, request.file_path)
    return ImportStepReceipt(payload=payload, obj=None)



def read_import_step_result(
    doc: MutationReadDocument, receipt: ImportStepReceipt, request: ImportStepRequest
) -> ImportStepInspection:
    path = receipt.payload.get("path")
    if not isinstance(path, str) or not path.strip():
        raise ImportStepError("INVALID_IMPORT_STEP_RESULT", "missing export path")
    return ImportStepInspection(payload=dict(receipt.payload))



def run_import_step(
    collaborators: ImportStepCollaborators,
    doc_name: str, file_path: str,
) -> ImportStepResult:
    """Run import_step through apply, recompute, inspection, and commit."""

    request = build_import_step_request(doc_name, file_path)
    if isinstance(request, dict):
        return request
    return _ImportStepExecution(collaborators, request).run()


class _ImportStepRpcFacade(Protocol):
    _cad_collaborators: ImportStepCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_import_step(
    self: _ImportStepRpcFacade,
    doc_name: str, file_path: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_import_step(collaborators, doc_name, file_path)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("import_step", rpc_import_step)


__all__ = [
    "ImportStepCollaborators",
    "ImportStepError",
    "ImportStepInspection",
    "ImportStepReceipt",
    "apply_import_step",
    "build_import_step_request",
    "read_import_step_result",
    "rpc_import_step",
    "run_import_step",
    "TYPED_RPC_HANDLER",
]
