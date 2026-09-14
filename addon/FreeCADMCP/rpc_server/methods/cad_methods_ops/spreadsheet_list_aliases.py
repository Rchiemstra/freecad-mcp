"""Typed ``spreadsheet_list_aliases`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.spreadsheet_list_aliases_contract import (
    SpreadsheetListAliasesCollaborators,
    SpreadsheetListAliasesDocument,
    SpreadsheetListAliasesFailure,
    SpreadsheetListAliasesName,
    SpreadsheetListAliasesReadDocument,
    SpreadsheetListAliasesRequest,
    SpreadsheetListAliasesResult,
    DocumentName,
    make_spreadsheet_list_aliases_failure,
    make_spreadsheet_list_aliases_success,
    make_spreadsheet_list_aliases_uncertain,
)
from .spreadsheet_list_aliases_mutation import SpreadsheetListAliasesError, run_spreadsheet_list_aliases_native_mutation
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
class SpreadsheetListAliasesReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    skipped: bool = False
    extra: object = None


@dataclass(frozen=True, slots=True)
class SpreadsheetListAliasesInspection:
    """Read-only data captured after the native-owned recompute."""

    name: SpreadsheetListAliasesName
    label: str
    extra: object = None


def _failure(error: SpreadsheetListAliasesError, *, retry_safe: bool = True) -> SpreadsheetListAliasesFailure:
    return make_spreadsheet_list_aliases_failure(error.code, str(error), retry_safe=retry_safe)


def apply_spreadsheet_list_aliases(doc: SpreadsheetListAliasesDocument, request: SpreadsheetListAliasesRequest) -> SpreadsheetListAliasesReceipt:
    """Capture the sheet identity; aliases are read after native recompute."""

    sheet = require_object(doc, request.sheet_name, missing_code="OBJECT_NOT_FOUND", error=SpreadsheetListAliasesError)
    return SpreadsheetListAliasesReceipt(name=object_name(sheet) or request.sheet_name, item=sheet, skipped=False)


def read_spreadsheet_list_aliases_result(doc: SpreadsheetListAliasesReadDocument, receipt: SpreadsheetListAliasesReceipt) -> SpreadsheetListAliasesInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        located = receipt.item
    if located is None:
        raise SpreadsheetListAliasesError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if (
        receipt.item is not None
        and located is not receipt.item
        and object_name(located) != receipt.name
    ):
        raise SpreadsheetListAliasesError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")

    aliases: dict[str, object] = {}
    extra = aliases

    return SpreadsheetListAliasesInspection(
        name=SpreadsheetListAliasesName(receipt.name),
        label=object_label(located),
        extra=extra,
    )


def build_spreadsheet_list_aliases_request(doc_name: object, sheet_name: object) -> SpreadsheetListAliasesRequest | SpreadsheetListAliasesFailure:
    doc_name_value = nonempty_string(doc_name, 'doc_name')
    if doc_name_value is None:
        return _failure(SpreadsheetListAliasesError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    sheet_name_value = nonempty_string(sheet_name, 'sheet_name')
    if sheet_name_value is None:
        return _failure(SpreadsheetListAliasesError("INVALID_ARGUMENT", "sheet_name must be a nonempty string"))
    return SpreadsheetListAliasesRequest(
        doc_name=DocumentName(doc_name_value),
        sheet_name=sheet_name_value,
    )


@dataclass(slots=True)
class _SpreadsheetListAliasesExecution:
    collaborators: SpreadsheetListAliasesCollaborators
    request: SpreadsheetListAliasesRequest
    created: SpreadsheetListAliasesReceipt | None = None
    inspected: SpreadsheetListAliasesInspection | None = None

    def apply(self, doc: SpreadsheetListAliasesDocument) -> None:
        self.created = apply_spreadsheet_list_aliases(doc, self.request)

    def inspect(self, doc: SpreadsheetListAliasesReadDocument) -> None:
        if self.created is None:
            raise SpreadsheetListAliasesError(
                "INVALID_SPREADSHEET_LIST_ALIASES_RESULT",
                "spreadsheet_list_aliases did not return an identity receipt",
            )
        self.inspected = read_spreadsheet_list_aliases_result(doc, self.created)

    def run(self) -> SpreadsheetListAliasesResult:
        result = run_spreadsheet_list_aliases_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_spreadsheet_list_aliases_uncertain(
                "SPREADSHEET_LIST_ALIASES_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        return make_spreadsheet_list_aliases_success(sheet=self.inspected.name)


def run_spreadsheet_list_aliases(
    collaborators: SpreadsheetListAliasesCollaborators,
    doc_name: object, sheet_name: object,
) -> SpreadsheetListAliasesResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_spreadsheet_list_aliases_request(doc_name, sheet_name)
    if isinstance(request, dict):
        return request
    return _SpreadsheetListAliasesExecution(collaborators, request).run()


class _SpreadsheetListAliasesRpcFacade(Protocol):
    _cad_collaborators: SpreadsheetListAliasesCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_spreadsheet_list_aliases(
    self: _SpreadsheetListAliasesRpcFacade, doc_name: str, sheet_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_spreadsheet_list_aliases(collaborators, doc_name, sheet_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("spreadsheet_list_aliases", rpc_spreadsheet_list_aliases)


__all__ = [
    "SpreadsheetListAliasesCollaborators",
    "SpreadsheetListAliasesError",
    "SpreadsheetListAliasesInspection",
    "SpreadsheetListAliasesReceipt",
    "apply_spreadsheet_list_aliases",
    "build_spreadsheet_list_aliases_request",
    "read_spreadsheet_list_aliases_result",
    "rpc_spreadsheet_list_aliases",
    "run_spreadsheet_list_aliases",
    "TYPED_RPC_HANDLER",
]
