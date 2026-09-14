"""Typed ``insert_part_from_library`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.insert_part_from_library_contract import (
    DocumentName,
    InsertPartFromLibraryCollaborators,
    InsertPartFromLibraryFailure,
    InsertPartFromLibraryRequest,
    InsertPartFromLibraryResult,
    make_insert_part_from_library_failure,
    make_insert_part_from_library_success,
    make_insert_part_from_library_uncertain,
)
from .insert_part_from_library_mutation import (
    InsertPartFromLibraryError,
    run_insert_part_from_library_native_mutation,
)
from .typed_rpc_document import document_name, object_names


@dataclass(frozen=True, slots=True)
class InsertPartFromLibraryReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    relative_path: str
    added: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InsertPartFromLibraryInspection:
    """Read-only data captured after the native-owned recompute."""

    name: DocumentName
    relative_path: str


def _failure(
    error: InsertPartFromLibraryError, *, retry_safe: bool = True
) -> InsertPartFromLibraryFailure:
    return make_insert_part_from_library_failure(
        error.code, str(error), retry_safe=retry_safe, diagnostics=error.diagnostics
    )


def apply_insert_part_from_library(
    doc: object,
    request: InsertPartFromLibraryRequest,
    insert: Callable[[str, str], object] | None,
) -> InsertPartFromLibraryReceipt:
    """Insert a library part without recomputing or managing a transaction."""

    before = set(object_names(doc))
    if insert is None:
        raise InsertPartFromLibraryError(
            "INSERT_UNAVAILABLE",
            "insert_part_from_library collaborator is missing",
        )
    insert(str(request.doc_name), request.relative_path)
    added = tuple(sorted(set(object_names(doc)) - before))
    return InsertPartFromLibraryReceipt(
        name=document_name(doc),
        relative_path=request.relative_path,
        added=added,
    )


def read_insert_part_from_library_result(
    doc: object, receipt: InsertPartFromLibraryReceipt
) -> InsertPartFromLibraryInspection:
    """Build the public result after the shared mutation recompute."""

    missing = [name for name in receipt.added if name not in object_names(doc)]
    if missing:
        raise InsertPartFromLibraryError(
            "INSERTED_OBJECT_MISSING",
            f"Inserted objects are missing: {missing!r}",
        )
    return InsertPartFromLibraryInspection(
        name=DocumentName(document_name(doc)),
        relative_path=receipt.relative_path,
    )


def build_insert_part_from_library_request(
    doc_name: object, relative_path: object
) -> InsertPartFromLibraryRequest | InsertPartFromLibraryFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(
            InsertPartFromLibraryError("INVALID_ARGUMENT", "doc_name must be a nonempty string")
        )
    if not isinstance(relative_path, str) or not relative_path.strip():
        return _failure(
            InsertPartFromLibraryError(
                "INVALID_ARGUMENT", "relative_path must be a nonempty string"
            )
        )
    return InsertPartFromLibraryRequest(
        doc_name=DocumentName(doc_name),
        relative_path=relative_path,
    )


@dataclass(slots=True)
class _InsertPartFromLibraryExecution:
    collaborators: InsertPartFromLibraryCollaborators
    request: InsertPartFromLibraryRequest
    insert: Callable[[str, str], object] | None
    created: InsertPartFromLibraryReceipt | None = None
    inspected: InsertPartFromLibraryInspection | None = None

    def apply(self, doc: object) -> None:
        self.created = apply_insert_part_from_library(doc, self.request, self.insert)

    def inspect(self, doc: object) -> None:
        if self.created is None:
            raise InsertPartFromLibraryError(
                "INVALID_INSERT_PART_FROM_LIBRARY_RESULT",
                "Part insertion did not return an identity receipt",
            )
        self.inspected = read_insert_part_from_library_result(doc, self.created)

    def run(self) -> InsertPartFromLibraryResult:
        result = run_insert_part_from_library_native_mutation(
            self.collaborators,
            str(self.request.doc_name),
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_insert_part_from_library_uncertain(
                "INSERT_PART_FROM_LIBRARY_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected insert result",
                committed=True,
            )
        return make_insert_part_from_library_success(
            self.inspected.name, self.inspected.relative_path
        )


def run_insert_part_from_library(
    collaborators: InsertPartFromLibraryCollaborators,
    doc_name: object,
    relative_path: object,
) -> InsertPartFromLibraryResult:
    """Run library insertion through apply, recompute, inspection, and commit."""

    request = build_insert_part_from_library_request(doc_name, relative_path)
    if isinstance(request, dict):
        return request
    inserter = getattr(collaborators, "insert_part_from_library", None)
    insert = inserter if callable(inserter) else None
    return _InsertPartFromLibraryExecution(collaborators, request, insert).run()


class _InsertPartFromLibraryRpcFacade(Protocol):
    _cad_collaborators: InsertPartFromLibraryCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_insert_part_from_library(
    self: _InsertPartFromLibraryRpcFacade,
    doc_name: str,
    relative_path: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_insert_part_from_library(collaborators, doc_name, relative_path)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("insert_part_from_library", rpc_insert_part_from_library)


__all__ = [
    "InsertPartFromLibraryCollaborators",
    "InsertPartFromLibraryError",
    "InsertPartFromLibraryInspection",
    "InsertPartFromLibraryReceipt",
    "apply_insert_part_from_library",
    "build_insert_part_from_library_request",
    "read_insert_part_from_library_result",
    "rpc_insert_part_from_library",
    "run_insert_part_from_library",
    "TYPED_RPC_HANDLER",
]
