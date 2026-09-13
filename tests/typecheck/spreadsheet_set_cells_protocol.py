"""Static contract examples for the spreadsheet_set_cells collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.spreadsheet_set_cells_contract import (
    SpreadsheetSetCellsRequest,
    SpreadsheetSetCellsSuccess,
    SpreadsheetSetCellsDocument,
    SpreadsheetSetCellsName,
    SpreadsheetSetCellsReadDocument,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.spreadsheet_set_cells import (
    SpreadsheetSetCellsCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.spreadsheet_set_cells import spreadsheet_set_cells_operation


class CompleteSpreadsheetSetCellsDouble:
    """A test double that satisfies every dependency."""

    def validate_document_invariants(self, document: SpreadsheetSetCellsReadDocument) -> object:
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

    def validate_document_invariants(self, document: SpreadsheetSetCellsReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


complete: SpreadsheetSetCellsCollaborators = CompleteSpreadsheetSetCellsDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> SpreadsheetSetCellsCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


missing_postcondition: SpreadsheetSetCellsCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
valid_request = SpreadsheetSetCellsRequest(doc_name=document_name, sheet_name="Value", cells=[{"address": "A1", "value": 1}])


def public_client_preserves_names(client: FreeCADConnection) -> None:
    assert_type(spreadsheet_set_cells_operation(client, True, "Doc", "Value", [{"address": "A1", "value": 1}]), CallToolResult)


def postcondition_surface_is_read_only(document: SpreadsheetSetCellsReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    item = document.getObject("Body")
    if item is not None:
        item.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
