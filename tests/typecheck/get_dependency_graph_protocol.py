"""Static contract examples for the get_dependency_graph collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.get_dependency_graph_contract import (
    GetDependencyGraphRequest,
    GetDependencyGraphSuccess,
    MutationReadDocument,
    DocumentName,
    ObjectName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.get_dependency_graph import (
    GetDependencyGraphCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.get_dependency_graph_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp._shared.protocol.get_dependency_graph_contract import ObjectName as ClientSecond
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.get_dependency_graph import get_dependency_graph_operation


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


complete: GetDependencyGraphCollaborators = CompleteDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> GetDependencyGraphCollaborators:
    return collaborators


missing_postcondition: GetDependencyGraphCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]


_ = GetDependencyGraphRequest
incomplete_success: GetDependencyGraphSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    name = ClientSecond("Box")
    assert_type(client.get_dependency_graph(document, name), object)
    assert_type(get_dependency_graph_operation(client, "Doc", "Box"), CallToolResult)
    client.get_dependency_graph(0, "Box")  # type: ignore[arg-type]
    client.get_dependency_graph("Doc", 0)  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: MutationReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    body = document.getObject("Body")
    if body is not None:
        body.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
