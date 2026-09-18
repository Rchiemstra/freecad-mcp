
"""Typed ``spreadsheet_set_cells`` mutation."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

try:
    from ...._shared.protocol.spreadsheet_set_cells_contract import (
        DocumentName,
        SpreadsheetSetCellsCollaborators,
        SpreadsheetSetCellsDocument,
        SpreadsheetSetCellsFailure,
        SpreadsheetSetCellsName,
        SpreadsheetSetCellsReadDocument,
        SpreadsheetSetCellsRequest,
        SpreadsheetSetCellsResult,
        make_spreadsheet_set_cells_failure,
        make_spreadsheet_set_cells_success,
        make_spreadsheet_set_cells_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.spreadsheet_set_cells_contract import (
        DocumentName,
        SpreadsheetSetCellsCollaborators,
        SpreadsheetSetCellsDocument,
        SpreadsheetSetCellsFailure,
        SpreadsheetSetCellsName,
        SpreadsheetSetCellsReadDocument,
        SpreadsheetSetCellsRequest,
        SpreadsheetSetCellsResult,
        make_spreadsheet_set_cells_failure,
        make_spreadsheet_set_cells_success,
        make_spreadsheet_set_cells_uncertain,
    )
from .feature_mutate_support import is_read_only_property
from .spreadsheet_cell_ops import read_spreadsheet_cell
from .spreadsheet_set_cells_mutation import (
    SpreadsheetSetCellsError,
    run_spreadsheet_set_cells_native_mutation,
)
from .typed_rpc_support import (
    nonempty_string,
    object_label,
    object_name,
    require_object,
)


@dataclass(frozen=True, slots=True)
class SpreadsheetSetCellsReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    skipped: bool = False
    extra: object = None


@dataclass(frozen=True, slots=True)
class SpreadsheetSetCellsInspection:
    """Read-only data captured after the native-owned recompute."""

    name: SpreadsheetSetCellsName
    label: str
    extra: object = None


def _failure(error: SpreadsheetSetCellsError, *, retry_safe: bool = True) -> SpreadsheetSetCellsFailure:
    return make_spreadsheet_set_cells_failure(error.code, str(error), retry_safe=retry_safe)


def _resolve_address_from_alias(sheet: object, alias: str) -> str | None:
    resolver = getattr(sheet, "getCellFromAlias", None)
    if not callable(resolver):
        return None
    try:
        resolved = resolver(alias)
    except Exception:
        return None
    return str(resolved) if resolved else None


def apply_spreadsheet_set_cells(doc: SpreadsheetSetCellsDocument, request: SpreadsheetSetCellsRequest) -> SpreadsheetSetCellsReceipt:
    """Write spreadsheet cells without recomputing."""

    sheet = require_object(doc, request.sheet_name, missing_code="OBJECT_NOT_FOUND", error=SpreadsheetSetCellsError)
    touched: list[dict[str, object]] = []
    if not isinstance(request.cells, list):
        raise SpreadsheetSetCellsError("INVALID_ARGUMENT", "cells must be a list")
    batch_aliases: dict[str, str] = {}
    for raw_cell in request.cells:
        if not isinstance(raw_cell, dict):
            raise SpreadsheetSetCellsError("INVALID_ARGUMENT", "each cell must be an object")
        cell: dict[str, object] = {}
        for key, value in raw_cell.items():
            if not isinstance(key, str):
                raise SpreadsheetSetCellsError("INVALID_ARGUMENT", "cell keys must be strings")
            cell[key] = value
        address = cell.get("address") or cell.get("addr")
        alias = cell.get("alias")
        if (not isinstance(address, str) or not address) and isinstance(alias, str) and alias:
            address = _resolve_address_from_alias(sheet, alias)
        if not isinstance(address, str) or not address:
            raise SpreadsheetSetCellsError("INVALID_ARGUMENT", "cell requires address or resolvable alias")
        if "value" in cell:
            setter = getattr(sheet, "set", None)
            if not callable(setter):
                raise SpreadsheetSetCellsError("INVALID_SHEET", "spreadsheet cannot set cells")
            setter(address, str(cell["value"]))
        alias_to_set = alias if isinstance(alias, str) and alias and cell.get("address") else cell.get("set_alias")
        if isinstance(alias_to_set, str) and alias_to_set:
            alias_setter = getattr(sheet, "setAlias", None)
            if not callable(alias_setter):
                raise SpreadsheetSetCellsError("INVALID_SHEET", "spreadsheet cannot set aliases")
            if alias_to_set in batch_aliases and batch_aliases[alias_to_set] != address:
                raise SpreadsheetSetCellsError(
                    "INVALID_ARGUMENT",
                    f"Duplicate alias in batch: {alias_to_set!r}",
                )
            existing_address = _resolve_address_from_alias(sheet, alias_to_set)
            if existing_address and existing_address != address:
                raise SpreadsheetSetCellsError(
                    "INVALID_ARGUMENT",
                    f"Alias already bound: {alias_to_set!r}",
                )
            if is_read_only_property(sheet, address):
                raise SpreadsheetSetCellsError("EXPRESSION_ERROR", f"{address!r} is read-only")
            try:
                alias_setter(address, alias_to_set)
            except Exception as exc:
                raise SpreadsheetSetCellsError("EXPRESSION_ERROR", str(exc) or type(exc).__name__) from exc
            batch_aliases[alias_to_set] = address
        touched.append(
            {
                "address": address,
                "requested_alias": alias_to_set if isinstance(alias_to_set, str) and alias_to_set else None,
            }
        )
    return SpreadsheetSetCellsReceipt(
        name=object_name(sheet) or request.sheet_name,
        item=sheet,
        skipped=False,
        extra=touched,
    )


def read_spreadsheet_set_cells_result(doc: SpreadsheetSetCellsReadDocument, receipt: SpreadsheetSetCellsReceipt) -> SpreadsheetSetCellsInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        located = receipt.item
    if located is None:
        raise SpreadsheetSetCellsError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if (
        receipt.item is not None
        and located is not receipt.item
        and object_name(located) != receipt.name
    ):
        raise SpreadsheetSetCellsError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")

    touched = receipt.extra
    if not isinstance(touched, list):
        raise SpreadsheetSetCellsError(
            "INVALID_SPREADSHEET_SET_CELLS_RESULT",
            "spreadsheet_set_cells receipt is missing touched addresses",
        )

    updated: list[dict[str, object]] = []
    for item in touched:
        if not isinstance(item, dict):
            raise SpreadsheetSetCellsError(
                "INVALID_SPREADSHEET_SET_CELLS_RESULT",
                "spreadsheet_set_cells receipt entry must be an object",
            )
        address = item.get("address")
        requested_alias = item.get("requested_alias")
        if not isinstance(address, str) or not address:
            raise SpreadsheetSetCellsError(
                "INVALID_SPREADSHEET_SET_CELLS_RESULT",
                "spreadsheet_set_cells receipt entry requires address",
            )
        row = read_spreadsheet_cell(located, {"address": address})
        if isinstance(requested_alias, str) and requested_alias:
            bound = row.get("alias")
            if str(bound or "") != requested_alias:
                raise SpreadsheetSetCellsError(
                    "EXPRESSION_ERROR",
                    f"Alias on {address!r} does not match the requested value",
                )
        updated.append(row)

    return SpreadsheetSetCellsInspection(
        name=SpreadsheetSetCellsName(receipt.name),
        label=object_label(located),
        extra=updated,
    )


def build_spreadsheet_set_cells_request(doc_name: object, sheet_name: object, cells: object) -> SpreadsheetSetCellsRequest | SpreadsheetSetCellsFailure:
    doc_name_value = nonempty_string(doc_name, 'doc_name')
    if doc_name_value is None:
        return _failure(SpreadsheetSetCellsError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    sheet_name_value = nonempty_string(sheet_name, 'sheet_name')
    if sheet_name_value is None:
        return _failure(SpreadsheetSetCellsError("INVALID_ARGUMENT", "sheet_name must be a nonempty string"))
    if not isinstance(cells, list) or not cells:
        return _failure(SpreadsheetSetCellsError("INVALID_ARGUMENT", "cells must be a non-empty list"))
    return SpreadsheetSetCellsRequest(
        doc_name=DocumentName(doc_name_value),
        sheet_name=sheet_name_value,
        cells=cells,
    )


@dataclass(slots=True)
class _SpreadsheetSetCellsExecution:
    collaborators: SpreadsheetSetCellsCollaborators
    request: SpreadsheetSetCellsRequest
    created: SpreadsheetSetCellsReceipt | None = None
    inspected: SpreadsheetSetCellsInspection | None = None

    def apply(self, doc: SpreadsheetSetCellsDocument) -> None:
        self.created = apply_spreadsheet_set_cells(doc, self.request)

    def inspect(self, doc: SpreadsheetSetCellsReadDocument) -> None:
        if self.created is None:
            raise SpreadsheetSetCellsError(
                "INVALID_SPREADSHEET_SET_CELLS_RESULT",
                "spreadsheet_set_cells did not return an identity receipt",
            )
        self.inspected = read_spreadsheet_set_cells_result(doc, self.created)

    def run(self) -> SpreadsheetSetCellsResult:
        result = run_spreadsheet_set_cells_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_spreadsheet_set_cells_uncertain(
                "SPREADSHEET_SET_CELLS_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        updated = self.inspected.extra
        if not isinstance(updated, list):
            return make_spreadsheet_set_cells_uncertain(
                "SPREADSHEET_SET_CELLS_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without inspected updated cells",
                committed=True,
            )
        return make_spreadsheet_set_cells_success(sheet=self.inspected.name, updated=updated)


def run_spreadsheet_set_cells(
    collaborators: SpreadsheetSetCellsCollaborators,
    doc_name: object, sheet_name: object, cells: object,
) -> SpreadsheetSetCellsResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_spreadsheet_set_cells_request(doc_name, sheet_name, cells)
    if isinstance(request, dict):
        return request
    return _SpreadsheetSetCellsExecution(collaborators, request).run()


class _SpreadsheetSetCellsRpcFacade(Protocol):
    _cad_collaborators: SpreadsheetSetCellsCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_spreadsheet_set_cells(
    self: _SpreadsheetSetCellsRpcFacade, doc_name: str, sheet_name: str, cells: object,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_spreadsheet_set_cells(collaborators, doc_name, sheet_name, cells)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("spreadsheet_set_cells", rpc_spreadsheet_set_cells)


__all__ = [
    "TYPED_RPC_HANDLER",
    "SpreadsheetSetCellsCollaborators",
    "SpreadsheetSetCellsError",
    "SpreadsheetSetCellsInspection",
    "SpreadsheetSetCellsReceipt",
    "apply_spreadsheet_set_cells",
    "build_spreadsheet_set_cells_request",
    "read_spreadsheet_set_cells_result",
    "rpc_spreadsheet_set_cells",
    "run_spreadsheet_set_cells",
]
