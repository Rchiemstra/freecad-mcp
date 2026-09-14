"""Static contract examples for the create_assembly collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.create_assembly_contract import (
    CreateAssemblyRequest,
    CreateAssemblySuccess,
    MutationReadDocument,
    DocumentName,
    AssemblyName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.create_assembly import (
    CreateAssemblyCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.create_assembly_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp._shared.protocol.create_assembly_contract import AssemblyName as ClientSecond
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.create_assembly import create_assembly_operation


class CompleteDouble:
    def validate_document_invariants(self, document: MutationReadDocument) -> object:
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
    def validate_document_invariants(self, document: MutationReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


complete: CreateAssemblyCollaborators = CompleteDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> CreateAssemblyCollaborators:
    return collaborators


missing_postcondition: CreateAssemblyCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]


_ = (CreateAssemblyRequest, DocumentName, AssemblyName)
incomplete_success: CreateAssemblySuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    name = ClientSecond("Assembly")
    assert_type(client.create_assembly(document, name), object)
    assert_type(create_assembly_operation(client, True, "Doc", "Assembly"), CallToolResult)
    client.create_assembly(name, document)  # type: ignore[arg-type]
    client.create_assembly("Doc", "Assembly")  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: MutationReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    body = document.getObject("Body")
    if body is not None:
        body.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
