"""Typed ``spreadsheet_set_alias`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.spreadsheet_set_alias_contract import (
    SpreadsheetSetAliasCollaborators,
    SpreadsheetSetAliasDocument,
    SpreadsheetSetAliasFailure,
    SpreadsheetSetAliasName,
    SpreadsheetSetAliasReadDocument,
    SpreadsheetSetAliasRequest,
    SpreadsheetSetAliasResult,
    DocumentName,
    make_spreadsheet_set_alias_failure,
    make_spreadsheet_set_alias_success,
    make_spreadsheet_set_alias_uncertain,
)
from .spreadsheet_set_alias_mutation import SpreadsheetSetAliasError, run_spreadsheet_set_alias_native_mutation
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
class SpreadsheetSetAliasReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    address: str
    alias: str
    skipped: bool = False
    extra: object = None


@dataclass(frozen=True, slots=True)
class SpreadsheetSetAliasInspection:
    """Read-only data captured after the native-owned recompute."""

    name: SpreadsheetSetAliasName
    label: str
    extra: object = None


def _failure(error: SpreadsheetSetAliasError, *, retry_safe: bool = True) -> SpreadsheetSetAliasFailure:
    return make_spreadsheet_set_alias_failure(error.code, str(error), retry_safe=retry_safe)


def apply_spreadsheet_set_alias(doc: SpreadsheetSetAliasDocument, request: SpreadsheetSetAliasRequest) -> SpreadsheetSetAliasReceipt:
    """Set a spreadsheet alias without recomputing."""

    sheet = require_object(doc, request.sheet_name, missing_code="OBJECT_NOT_FOUND", error=SpreadsheetSetAliasError)
    alias_setter = getattr(sheet, "setAlias", None)
    if not callable(alias_setter):
        raise SpreadsheetSetAliasError("INVALID_SHEET", "spreadsheet cannot set aliases")
    try:
        alias_setter(request.address, request.alias)
    except Exception as exc:
        raise SpreadsheetSetAliasError("EXPRESSION_ERROR", str(exc) or type(exc).__name__) from exc
    return SpreadsheetSetAliasReceipt(
        name=object_name(sheet) or request.sheet_name,
        item=sheet,
        address=request.address,
        alias=request.alias,
        skipped=False,
    )


def read_spreadsheet_set_alias_result(doc: SpreadsheetSetAliasReadDocument, receipt: SpreadsheetSetAliasReceipt) -> SpreadsheetSetAliasInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        raise SpreadsheetSetAliasError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if receipt.item is not None and located is not receipt.item:
        raise SpreadsheetSetAliasError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")
    getter = getattr(located, "getAlias", None)
    if callable(getter):
        bound = getter(receipt.address)
        if str(bound or "") != receipt.alias:
            raise SpreadsheetSetAliasError(
                "EXPRESSION_ERROR",
                f"Alias on {receipt.address!r} does not match the requested value",
            )

    extra = receipt.extra

    return SpreadsheetSetAliasInspection(
        name=SpreadsheetSetAliasName(receipt.name),
        label=object_label(located),
        extra=extra,
    )


def build_spreadsheet_set_alias_request(doc_name: object, sheet_name: object, address: object, alias: object) -> SpreadsheetSetAliasRequest | SpreadsheetSetAliasFailure:
    doc_name_value = nonempty_string(doc_name, 'doc_name')
    if doc_name_value is None:
        return _failure(SpreadsheetSetAliasError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    sheet_name_value = nonempty_string(sheet_name, 'sheet_name')
    if sheet_name_value is None:
        return _failure(SpreadsheetSetAliasError("INVALID_ARGUMENT", "sheet_name must be a nonempty string"))
    address_value = nonempty_string(address, 'address')
    if address_value is None:
        return _failure(SpreadsheetSetAliasError("INVALID_ARGUMENT", "address must be a nonempty string"))
    alias_value = nonempty_string(alias, 'alias')
    if alias_value is None:
        return _failure(SpreadsheetSetAliasError("INVALID_ARGUMENT", "alias must be a nonempty string"))
    return SpreadsheetSetAliasRequest(
        doc_name=DocumentName(doc_name_value),
        sheet_name=sheet_name_value,
        address=address_value,
        alias=alias_value,
    )


@dataclass(slots=True)
class _SpreadsheetSetAliasExecution:
    collaborators: SpreadsheetSetAliasCollaborators
    request: SpreadsheetSetAliasRequest
    created: SpreadsheetSetAliasReceipt | None = None
    inspected: SpreadsheetSetAliasInspection | None = None

    def apply(self, doc: SpreadsheetSetAliasDocument) -> None:
        self.created = apply_spreadsheet_set_alias(doc, self.request)

    def inspect(self, doc: SpreadsheetSetAliasReadDocument) -> None:
        if self.created is None:
            raise SpreadsheetSetAliasError(
                "INVALID_SPREADSHEET_SET_ALIAS_RESULT",
                "spreadsheet_set_alias did not return an identity receipt",
            )
        self.inspected = read_spreadsheet_set_alias_result(doc, self.created)

    def run(self) -> SpreadsheetSetAliasResult:
        result = run_spreadsheet_set_alias_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_spreadsheet_set_alias_uncertain(
                "SPREADSHEET_SET_ALIAS_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        return make_spreadsheet_set_alias_success(sheet=self.inspected.name, address=self.request.address, alias=self.request.alias)


def run_spreadsheet_set_alias(
    collaborators: SpreadsheetSetAliasCollaborators,
    doc_name: object, sheet_name: object, address: object, alias: object,
) -> SpreadsheetSetAliasResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_spreadsheet_set_alias_request(doc_name, sheet_name, address, alias)
    if isinstance(request, dict):
        return request
    return _SpreadsheetSetAliasExecution(collaborators, request).run()


class _SpreadsheetSetAliasRpcFacade(Protocol):
    _cad_collaborators: SpreadsheetSetAliasCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_spreadsheet_set_alias(
    self: _SpreadsheetSetAliasRpcFacade, doc_name: str, sheet_name: str, address: str, alias: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_spreadsheet_set_alias(collaborators, doc_name, sheet_name, address, alias)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("spreadsheet_set_alias", rpc_spreadsheet_set_alias)


__all__ = [
    "SpreadsheetSetAliasCollaborators",
    "SpreadsheetSetAliasError",
    "SpreadsheetSetAliasInspection",
    "SpreadsheetSetAliasReceipt",
    "apply_spreadsheet_set_alias",
    "build_spreadsheet_set_alias_request",
    "read_spreadsheet_set_alias_result",
    "rpc_spreadsheet_set_alias",
    "run_spreadsheet_set_alias",
    "TYPED_RPC_HANDLER",
]
