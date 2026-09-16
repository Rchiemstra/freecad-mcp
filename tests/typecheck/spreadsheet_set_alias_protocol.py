"""Static contract examples for the spreadsheet_set_alias collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.spreadsheet_set_alias_contract import (
    SpreadsheetSetAliasRequest,
    SpreadsheetSetAliasSuccess,
    SpreadsheetSetAliasDocument,
    SpreadsheetSetAliasName,
    SpreadsheetSetAliasReadDocument,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.spreadsheet_set_alias import (
    SpreadsheetSetAliasCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.spreadsheet_set_alias import spreadsheet_set_alias_operation


class CompleteSpreadsheetSetAliasDouble:
    """A test double that satisfies every dependency."""

    def validate_document_invariants(self, document: SpreadsheetSetAliasReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        postcondition: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


class MissingPostconditionDouble:
    """A stale double that cannot receive the native phase contract."""

    def validate_document_invariants(self, document: SpreadsheetSetAliasReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


complete: SpreadsheetSetAliasCollaborators = CompleteSpreadsheetSetAliasDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> SpreadsheetSetAliasCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


missing_postcondition: SpreadsheetSetAliasCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
valid_request = SpreadsheetSetAliasRequest(doc_name=document_name, sheet_name="Value", address="Value", alias="Value")


def public_client_preserves_names(client: FreeCADConnection) -> None:
    assert_type(spreadsheet_set_alias_operation(client, True, "Doc", "Value", "Value", "Value"), CallToolResult)


def postcondition_surface_is_read_only(document: SpreadsheetSetAliasReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    item = document.getObject("Body")
    if item is not None:
        item.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
