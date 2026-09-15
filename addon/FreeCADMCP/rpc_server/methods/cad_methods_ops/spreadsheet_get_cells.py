"""Typed ``spreadsheet_get_cells`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ...._shared.protocol.spreadsheet_get_cells_contract import (
    DocumentName,
    SpreadsheetGetCellsCollaborators,
    SpreadsheetGetCellsFailure,
    SpreadsheetGetCellsRequest,
    SpreadsheetGetCellsResult,
    make_spreadsheet_get_cells_failure,
    make_spreadsheet_get_cells_success,
)
from .policy_runtime import app_from, lookup_document, lookup_object, optional_recompute
from .spreadsheet_cell_ops import read_spreadsheet_cell
from .typed_rpc_support import nonempty_string


class SpreadsheetGetCellsError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: SpreadsheetGetCellsError, *, retry_safe: bool = True) -> SpreadsheetGetCellsFailure:
    return make_spreadsheet_get_cells_failure(error.code, str(error), retry_safe=retry_safe)


def build_spreadsheet_get_cells_request(
    doc_name: object, sheet_name: object, addresses: object
) -> SpreadsheetGetCellsRequest | SpreadsheetGetCellsFailure:
    doc_name_value = nonempty_string(doc_name, "doc_name")
    if doc_name_value is None:
        return _failure(SpreadsheetGetCellsError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    sheet_name_value = nonempty_string(sheet_name, "sheet_name")
    if sheet_name_value is None:
        return _failure(SpreadsheetGetCellsError("INVALID_ARGUMENT", "sheet_name must be a nonempty string"))
    if not isinstance(addresses, list) or not addresses:
        return _failure(SpreadsheetGetCellsError("INVALID_ARGUMENT", "addresses must be a non-empty list"))
    return SpreadsheetGetCellsRequest(
        doc_name=DocumentName(doc_name_value),
        sheet_name=sheet_name_value,
        addresses=addresses,
    )


def run_spreadsheet_get_cells(
    collaborators: SpreadsheetGetCellsCollaborators,
    doc_name: object,
    sheet_name: object,
    addresses: object,
) -> SpreadsheetGetCellsResult:
    request = build_spreadsheet_get_cells_request(doc_name, sheet_name, addresses)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(SpreadsheetGetCellsError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(
            SpreadsheetGetCellsError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}")
        )
    sheet = lookup_object(document, request.sheet_name)
    if sheet is None:
        return _failure(SpreadsheetGetCellsError("OBJECT_NOT_FOUND", "Object not found"))
    optional_recompute(collaborators, document)
    cells: list[dict[str, object]] = []
    for item in request.addresses:
        try:
            row = read_spreadsheet_cell(sheet, item)
        except Exception as exc:
            return _failure(
                SpreadsheetGetCellsError("SPREADSHEET_GET_CELLS_FAILED", str(exc) or type(exc).__name__)
            )
        cells.append({str(key): value for key, value in row.items()})
    return make_spreadsheet_get_cells_success(sheet=request.sheet_name, cells=cells)


class _SpreadsheetGetCellsRpcFacade(Protocol):
    _cad_collaborators: SpreadsheetGetCellsCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_spreadsheet_get_cells(
    self: _SpreadsheetGetCellsRpcFacade,
    doc_name: str,
    sheet_name: str,
    addresses: object,
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
    "build_spreadsheet_get_cells_request",
    "rpc_spreadsheet_get_cells",
    "run_spreadsheet_get_cells",
    "TYPED_RPC_HANDLER",
]
