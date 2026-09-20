"""Typed ``import_brep`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

try:
    from ...._shared.protocol.import_brep_contract import (
        ObjectName,
        DocumentName,
        ImportBrepCollaborators,
        ImportBrepFailure,
        ImportBrepRequest,
        ImportBrepResult,
        MutationDocument,
        MutationObject,
        MutationReadDocument,
        make_import_brep_failure,
        make_import_brep_success,
        make_import_brep_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.import_brep_contract import (
        ObjectName,
        DocumentName,
        ImportBrepCollaborators,
        ImportBrepFailure,
        ImportBrepRequest,
        ImportBrepResult,
        MutationDocument,
        MutationObject,
        MutationReadDocument,
        make_import_brep_failure,
        make_import_brep_success,
        make_import_brep_uncertain,
    )
from .typed_runtime import as_float, as_int, as_str
from . import measure_io_actions
from .import_brep_mutation import ImportBrepError, run_import_brep_native_mutation


@dataclass(frozen=True, slots=True)
class ImportBrepReceipt:
    payload: dict[str, object]
    obj: MutationObject | None


@dataclass(frozen=True, slots=True)
class ImportBrepInspection:
    payload: dict[str, object]


def _failure(error: ImportBrepError, *, retry_safe: bool = True) -> ImportBrepFailure:
    return make_import_brep_failure(error.code, str(error), retry_safe=retry_safe)


def build_import_brep_request(
    doc_name: object, file_path: object, obj_name: object
) -> ImportBrepRequest | ImportBrepFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(ImportBrepError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(file_path, str) or not file_path.strip():
        return _failure(ImportBrepError("INVALID_ARGUMENT", "file_path must be a nonempty string"))
    if obj_name is None:
        obj_name_value = "BRepImport"
    elif not isinstance(obj_name, str) or not obj_name.strip():
        return _failure(ImportBrepError("INVALID_ARGUMENT", "obj_name must be a nonempty string"))
    else:
        obj_name_value = obj_name
    request = ImportBrepRequest(
        doc_name=DocumentName(doc_name),
        file_path=file_path,
        obj_name=ObjectName(obj_name_value)
    )
    return request


@dataclass(slots=True)
class _ImportBrepExecution:
    collaborators: ImportBrepCollaborators
    request: ImportBrepRequest
    created: ImportBrepReceipt | None = None
    inspected: ImportBrepInspection | None = None

    def apply(self, doc: MutationDocument) -> None:
        self.created = apply_import_brep(doc, self.request)

    def inspect(self, doc: MutationReadDocument) -> None:
        if self.created is None:
            raise ImportBrepError(
                "INVALID_IMPORT_BREP_RESULT",
                "import_brep did not return an identity receipt",
            )
        self.inspected = read_import_brep_result(doc, self.created, self.request)

    def run(self) -> ImportBrepResult:
        result = run_import_brep_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_import_brep_uncertain(
                "IMPORT_BREP_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected import_brep result",
                committed=True,
            )
        payload = self.inspected.payload
        return make_import_brep_success(
            path=as_str(payload["path"]), object=as_str(payload["object"]), imported=bool(payload["imported"])
        )


def apply_import_brep(doc: MutationDocument, request: ImportBrepRequest) -> ImportBrepReceipt:
    """Apply import_brep without recomputing or managing a transaction."""

    payload = measure_io_actions.import_brep(doc, request.file_path, request.obj_name)
    target = payload.get("object")
    found = doc.getObject(str(target)) if isinstance(target, str) else None
    return ImportBrepReceipt(payload=dict(payload), obj=found)



def read_import_brep_result(
    doc: MutationReadDocument, receipt: ImportBrepReceipt, request: ImportBrepRequest
) -> ImportBrepInspection:
    key = "object"
    name = receipt.payload.get(key)
    if not isinstance(name, str) or not name.strip():
        raise ImportBrepError("INVALID_IMPORT_BREP_RESULT", "missing created identity")
    obj = doc.getObject(name)
    if obj is None:
        raise ImportBrepError("CREATED_OBJECT_MISSING", f"Created object is missing: {name!r}")
    if receipt.obj is not None and obj is not receipt.obj:
        raise ImportBrepError("CREATED_OBJECT_REPLACED", f"Created object was replaced: {name!r}")

    payload = dict(receipt.payload)
    if hasattr(obj, "Label") and "label" in payload:
        payload["label"] = str(obj.Label)
    return ImportBrepInspection(payload=payload)



def run_import_brep(
    collaborators: ImportBrepCollaborators,
    doc_name: str, file_path: str, obj_name: str = "BRepImport",
) -> ImportBrepResult:
    """Run import_brep through apply, recompute, inspection, and commit."""

    request = build_import_brep_request(doc_name, file_path, obj_name)
    if isinstance(request, dict):
        return request
    return _ImportBrepExecution(collaborators, request).run()


class _ImportBrepRpcFacade(Protocol):
    _cad_collaborators: ImportBrepCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_import_brep(
    self: _ImportBrepRpcFacade,
    doc_name: str, file_path: str, obj_name: str = "BRepImport",
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_import_brep(collaborators, doc_name, file_path, obj_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("import_brep", rpc_import_brep)


__all__ = [
    "ImportBrepCollaborators",
    "ImportBrepError",
    "ImportBrepInspection",
    "ImportBrepReceipt",
    "apply_import_brep",
    "build_import_brep_request",
    "read_import_brep_result",
    "rpc_import_brep",
    "run_import_brep",
    "TYPED_RPC_HANDLER",
]
