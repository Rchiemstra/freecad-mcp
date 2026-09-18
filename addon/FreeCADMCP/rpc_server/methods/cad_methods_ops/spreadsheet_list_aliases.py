"""Typed ``spreadsheet_list_aliases`` query handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

try:
    from ...._shared.protocol.spreadsheet_list_aliases_contract import (
        DocumentName,
        SpreadsheetListAliasesCollaborators,
        SpreadsheetListAliasesFailure,
        SpreadsheetListAliasesRequest,
        SpreadsheetListAliasesResult,
        make_spreadsheet_list_aliases_failure,
        make_spreadsheet_list_aliases_success,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.spreadsheet_list_aliases_contract import (
        DocumentName,
        SpreadsheetListAliasesCollaborators,
        SpreadsheetListAliasesFailure,
        SpreadsheetListAliasesRequest,
        SpreadsheetListAliasesResult,
        make_spreadsheet_list_aliases_failure,
        make_spreadsheet_list_aliases_success,
    )
from .policy_runtime import app_from, lookup_document, lookup_object, optional_recompute
from .spreadsheet_alias_ops import collect_spreadsheet_aliases
from .typed_rpc_support import nonempty_string


class SpreadsheetListAliasesError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _failure(error: SpreadsheetListAliasesError, *, retry_safe: bool = True) -> SpreadsheetListAliasesFailure:
    return make_spreadsheet_list_aliases_failure(error.code, str(error), retry_safe=retry_safe)


def build_spreadsheet_list_aliases_request(
    doc_name: object, sheet_name: object
) -> SpreadsheetListAliasesRequest | SpreadsheetListAliasesFailure:
    doc_name_value = nonempty_string(doc_name, "doc_name")
    if doc_name_value is None:
        return _failure(SpreadsheetListAliasesError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    sheet_name_value = nonempty_string(sheet_name, "sheet_name")
    if sheet_name_value is None:
        return _failure(SpreadsheetListAliasesError("INVALID_ARGUMENT", "sheet_name must be a nonempty string"))
    return SpreadsheetListAliasesRequest(
        doc_name=DocumentName(doc_name_value),
        sheet_name=sheet_name_value,
    )


def run_spreadsheet_list_aliases(
    collaborators: SpreadsheetListAliasesCollaborators,
    doc_name: object,
    sheet_name: object,
) -> SpreadsheetListAliasesResult:
    request = build_spreadsheet_list_aliases_request(doc_name, sheet_name)
    if isinstance(request, dict):
        return request
    app = app_from(collaborators)
    if app is None:
        return _failure(SpreadsheetListAliasesError("FREECAD_UNAVAILABLE", "FreeCAD collaborator is missing"))
    document = lookup_document(app, str(request.doc_name))
    if document is None:
        return _failure(
            SpreadsheetListAliasesError("DOCUMENT_NOT_FOUND", f"Document not found: {request.doc_name!r}")
        )
    sheet = lookup_object(document, request.sheet_name)
    if sheet is None:
        return _failure(SpreadsheetListAliasesError("OBJECT_NOT_FOUND", "Object not found"))
    optional_recompute(collaborators, document)
    try:
        aliases = collect_spreadsheet_aliases(sheet)
    except Exception as exc:
        return _failure(
            SpreadsheetListAliasesError("SPREADSHEET_LIST_ALIASES_FAILED", str(exc) or type(exc).__name__)
        )
    return make_spreadsheet_list_aliases_success(sheet=request.sheet_name, aliases=aliases)


class _SpreadsheetListAliasesRpcFacade(Protocol):
    _cad_collaborators: SpreadsheetListAliasesCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_spreadsheet_list_aliases(
    self: _SpreadsheetListAliasesRpcFacade,
    doc_name: str,
    sheet_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(lambda: run_spreadsheet_list_aliases(collaborators, doc_name, sheet_name))
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("spreadsheet_list_aliases", rpc_spreadsheet_list_aliases)


__all__ = [
    "SpreadsheetListAliasesCollaborators",
    "SpreadsheetListAliasesError",
    "build_spreadsheet_list_aliases_request",
    "rpc_spreadsheet_list_aliases",
    "run_spreadsheet_list_aliases",
    "TYPED_RPC_HANDLER",
]
