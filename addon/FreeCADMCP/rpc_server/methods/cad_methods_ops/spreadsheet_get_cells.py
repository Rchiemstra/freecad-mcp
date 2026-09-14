"""Typed ``spreadsheet_get_cells`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.spreadsheet_get_cells_contract import (
    SpreadsheetGetCellsCollaborators,
    SpreadsheetGetCellsDocument,
    SpreadsheetGetCellsFailure,
    SpreadsheetGetCellsName,
    SpreadsheetGetCellsReadDocument,
    SpreadsheetGetCellsRequest,
    SpreadsheetGetCellsResult,
    DocumentName,
    make_spreadsheet_get_cells_failure,
    make_spreadsheet_get_cells_success,
    make_spreadsheet_get_cells_uncertain,
)
from .spreadsheet_get_cells_mutation import SpreadsheetGetCellsError, run_spreadsheet_get_cells_native_mutation
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
class SpreadsheetGetCellsReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    skipped: bool = False
    extra: object = None


@dataclass(frozen=True, slots=True)
class SpreadsheetGetCellsInspection:
    """Read-only data captured after the native-owned recompute."""

    name: SpreadsheetGetCellsName
    label: str
    extra: object = None


def _failure(error: SpreadsheetGetCellsError, *, retry_safe: bool = True) -> SpreadsheetGetCellsFailure:
    return make_spreadsheet_get_cells_failure(error.code, str(error), retry_safe=retry_safe)


def apply_spreadsheet_get_cells(doc: SpreadsheetGetCellsDocument, request: SpreadsheetGetCellsRequest) -> SpreadsheetGetCellsReceipt:
    """Capture the sheet identity; values are read after native recompute."""

    sheet = require_object(doc, request.sheet_name, missing_code="OBJECT_NOT_FOUND", error=SpreadsheetGetCellsError)
    return SpreadsheetGetCellsReceipt(name=object_name(sheet) or request.sheet_name, item=sheet, skipped=False, extra=request.addresses)


def read_spreadsheet_get_cells_result(doc: SpreadsheetGetCellsReadDocument, receipt: SpreadsheetGetCellsReceipt) -> SpreadsheetGetCellsInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        located = receipt.item
    if located is None:
        raise SpreadsheetGetCellsError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if (
        receipt.item is not None
        and located is not receipt.item
        and object_name(located) != receipt.name
    ):
        raise SpreadsheetGetCellsError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")

    cells: list[object] = []
    addresses = receipt.extra if isinstance(receipt.extra, list) else []
    for item in addresses:
        address: object = item
        if isinstance(item, dict):
            address = item.get("address") or item.get("alias")
        row: dict[str, object] = {"address": str(address)}
        getter = getattr(located, "get", None)
        if callable(getter) and isinstance(address, str):
            try:
                row["value"] = getter(address)
            except Exception as exc:
                row["value_error"] = str(exc)
        cells.append(row)
    extra = cells

    return SpreadsheetGetCellsInspection(
        name=SpreadsheetGetCellsName(receipt.name),
        label=object_label(located),
        extra=extra,
    )


def build_spreadsheet_get_cells_request(doc_name: object, sheet_name: object, addresses: object) -> SpreadsheetGetCellsRequest | SpreadsheetGetCellsFailure:
    doc_name_value = nonempty_string(doc_name, 'doc_name')
    if doc_name_value is None:
        return _failure(SpreadsheetGetCellsError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    sheet_name_value = nonempty_string(sheet_name, 'sheet_name')
    if sheet_name_value is None:
        return _failure(SpreadsheetGetCellsError("INVALID_ARGUMENT", "sheet_name must be a nonempty string"))
    if not isinstance(addresses, list) or not addresses:
        return _failure(SpreadsheetGetCellsError("INVALID_ARGUMENT", "addresses must be a non-empty list"))
    return SpreadsheetGetCellsRequest(
        doc_name=DocumentName(doc_name_value),
        sheet_name=sheet_name_value,
        addresses=addresses,
    )


@dataclass(slots=True)
class _SpreadsheetGetCellsExecution:
    collaborators: SpreadsheetGetCellsCollaborators
    request: SpreadsheetGetCellsRequest
    created: SpreadsheetGetCellsReceipt | None = None
    inspected: SpreadsheetGetCellsInspection | None = None

    def apply(self, doc: SpreadsheetGetCellsDocument) -> None:
        self.created = apply_spreadsheet_get_cells(doc, self.request)

    def inspect(self, doc: SpreadsheetGetCellsReadDocument) -> None:
        if self.created is None:
            raise SpreadsheetGetCellsError(
                "INVALID_SPREADSHEET_GET_CELLS_RESULT",
                "spreadsheet_get_cells did not return an identity receipt",
            )
        self.inspected = read_spreadsheet_get_cells_result(doc, self.created)

    def run(self) -> SpreadsheetGetCellsResult:
        result = run_spreadsheet_get_cells_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_spreadsheet_get_cells_uncertain(
                "SPREADSHEET_GET_CELLS_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        return make_spreadsheet_get_cells_success(sheet=self.inspected.name)


def run_spreadsheet_get_cells(
    collaborators: SpreadsheetGetCellsCollaborators,
    doc_name: object, sheet_name: object, addresses: object,
) -> SpreadsheetGetCellsResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_spreadsheet_get_cells_request(doc_name, sheet_name, addresses)
    if isinstance(request, dict):
        return request
    return _SpreadsheetGetCellsExecution(collaborators, request).run()


class _SpreadsheetGetCellsRpcFacade(Protocol):
    _cad_collaborators: SpreadsheetGetCellsCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_spreadsheet_get_cells(
    self: _SpreadsheetGetCellsRpcFacade, doc_name: str, sheet_name: str, addresses: object,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_spreadsheet_get_cells(collaborators, doc_name, sheet_name, addresses)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("spreadsheet_get_cells", rpc_spreadsheet_get_cells)


__all__ = [
    "SpreadsheetGetCellsCollaborators",
    "SpreadsheetGetCellsError",
    "SpreadsheetGetCellsInspection",
    "SpreadsheetGetCellsReceipt",
    "apply_spreadsheet_get_cells",
    "build_spreadsheet_get_cells_request",
    "read_spreadsheet_get_cells_result",
    "rpc_spreadsheet_get_cells",
    "run_spreadsheet_get_cells",
    "TYPED_RPC_HANDLER",
]
