"""Typed ``spreadsheet_create`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.spreadsheet_create_contract import (
    SpreadsheetCreateCollaborators,
    SpreadsheetCreateDocument,
    SpreadsheetCreateFailure,
    SpreadsheetCreateName,
    SpreadsheetCreateReadDocument,
    SpreadsheetCreateRequest,
    SpreadsheetCreateResult,
    DocumentName,
    make_spreadsheet_create_failure,
    make_spreadsheet_create_success,
    make_spreadsheet_create_uncertain,
)
from .spreadsheet_create_mutation import SpreadsheetCreateError, run_spreadsheet_create_native_mutation
from .typed_rpc_support import (
    add_named_object,
    add_to_container,
    as_bool,
    as_float,
    as_int,
    assign_attr,
    call_named,
    invoke,
    nonempty_string,
    object_label,
    object_name,
    object_type_id,
    optional_string,
    parse_ref,
    remove_from_container,
    require_object,
    resolve_if_exists,
    snapshot_ring
)


@dataclass(frozen=True, slots=True)
class SpreadsheetCreateReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    skipped: bool = False
    extra: object = None


@dataclass(frozen=True, slots=True)
class SpreadsheetCreateInspection:
    """Read-only data captured after the native-owned recompute."""

    name: SpreadsheetCreateName
    label: str
    extra: object = None


def _failure(error: SpreadsheetCreateError, *, retry_safe: bool = True) -> SpreadsheetCreateFailure:
    return make_spreadsheet_create_failure(error.code, str(error), retry_safe=retry_safe)


def apply_spreadsheet_create(doc: SpreadsheetCreateDocument, request: SpreadsheetCreateRequest) -> SpreadsheetCreateReceipt:
    """Apply the mutation without recomputing or managing a transaction."""

    skipped = resolve_if_exists(doc, request.sheet_name, "error", error=SpreadsheetCreateError)
    if skipped is not None:
        return SpreadsheetCreateReceipt(name=object_name(skipped) or request.sheet_name, item=skipped, skipped=True)
    created = add_named_object(doc, 'Spreadsheet::Sheet', request.sheet_name)
    return SpreadsheetCreateReceipt(name=object_name(created) or request.sheet_name, item=created, skipped=False)


def read_spreadsheet_create_result(doc: SpreadsheetCreateReadDocument, receipt: SpreadsheetCreateReceipt) -> SpreadsheetCreateInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        located = receipt.item
    if located is None:
        raise SpreadsheetCreateError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if (
        receipt.item is not None
        and located is not receipt.item
        and object_name(located) != receipt.name
    ):
        raise SpreadsheetCreateError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")

    type_id = object_type_id(located)
    if 'Spreadsheet' not in type_id and type_id:
        raise SpreadsheetCreateError("CREATED_OBJECT_WRONG_TYPE", f"Created object is not Spreadsheet: {receipt.name!r}")

    extra = receipt.extra

    return SpreadsheetCreateInspection(
        name=SpreadsheetCreateName(receipt.name),
        label=object_label(located),
        extra=extra,
    )


def build_spreadsheet_create_request(doc_name: object, sheet_name: object) -> SpreadsheetCreateRequest | SpreadsheetCreateFailure:
    doc_name_value = nonempty_string(doc_name, 'doc_name')
    if doc_name_value is None:
        return _failure(SpreadsheetCreateError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    sheet_name_value = nonempty_string(sheet_name, 'sheet_name')
    if sheet_name_value is None:
        return _failure(SpreadsheetCreateError("INVALID_ARGUMENT", "sheet_name must be a nonempty string"))
    return SpreadsheetCreateRequest(
        doc_name=DocumentName(doc_name_value),
        sheet_name=sheet_name_value,
    )


@dataclass(slots=True)
class _SpreadsheetCreateExecution:
    collaborators: SpreadsheetCreateCollaborators
    request: SpreadsheetCreateRequest
    created: SpreadsheetCreateReceipt | None = None
    inspected: SpreadsheetCreateInspection | None = None

    def apply(self, doc: SpreadsheetCreateDocument) -> None:
        self.created = apply_spreadsheet_create(doc, self.request)

    def inspect(self, doc: SpreadsheetCreateReadDocument) -> None:
        if self.created is None:
            raise SpreadsheetCreateError(
                "INVALID_SPREADSHEET_CREATE_RESULT",
                "spreadsheet_create did not return an identity receipt",
            )
        self.inspected = read_spreadsheet_create_result(doc, self.created)

    def run(self) -> SpreadsheetCreateResult:
        result = run_spreadsheet_create_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_spreadsheet_create_uncertain(
                "SPREADSHEET_CREATE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        return make_spreadsheet_create_success(sheet=self.inspected.name, label=self.inspected.label)


def run_spreadsheet_create(
    collaborators: SpreadsheetCreateCollaborators,
    doc_name: object, sheet_name: object,
) -> SpreadsheetCreateResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_spreadsheet_create_request(doc_name, sheet_name)
    if isinstance(request, dict):
        return request
    return _SpreadsheetCreateExecution(collaborators, request).run()


class _SpreadsheetCreateRpcFacade(Protocol):
    _cad_collaborators: SpreadsheetCreateCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_spreadsheet_create(
    self: _SpreadsheetCreateRpcFacade, doc_name: str, sheet_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_spreadsheet_create(collaborators, doc_name, sheet_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("spreadsheet_create", rpc_spreadsheet_create)


__all__ = [
    "SpreadsheetCreateCollaborators",
    "SpreadsheetCreateError",
    "SpreadsheetCreateInspection",
    "SpreadsheetCreateReceipt",
    "apply_spreadsheet_create",
    "build_spreadsheet_create_request",
    "read_spreadsheet_create_result",
    "rpc_spreadsheet_create",
    "run_spreadsheet_create",
    "TYPED_RPC_HANDLER",
]
