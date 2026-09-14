"""Static contract examples for the repair_references collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.repair_references_contract import (
    RepairReferencesCollaborators,
    RepairReferencesReadDocument,
    RepairReferencesRequest,
    RepairReferencesSuccess,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.repair_references import (
    RepairReferencesCollaborators as LeafCollaborators,
)
from freecad_mcp._shared.protocol.repair_references_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.repair_references import repair_references_operation


class CompleteDouble:
    def validate_document_invariants(self, document: RepairReferencesReadDocument) -> object:
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
    def validate_document_invariants(self, document: RepairReferencesReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
    ) -> object:
        return None


complete: LeafCollaborators = CompleteDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> LeafCollaborators:
    return collaborators


missing_postcondition: LeafCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
valid_request = RepairReferencesRequest(doc_name=document_name, repairs=(), recompute=False, validate=False)
incomplete_success: RepairReferencesSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    assert_type(client.repair_references(document, ()), object)
    assert_type(repair_references_operation(client, 'Doc', []), CallToolResult)
    client.repair_references(123, 123)  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: RepairReferencesReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]


__all__: list[str] = []
