"""Static contract examples for the export_brep collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.export_brep_contract import (
    ExportBrepRequest,
    ExportBrepSuccess,
    MutationReadDocument,
    DocumentName,
    ObjectName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.export_brep import (
    ExportBrepCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.export_brep_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp._shared.protocol.export_brep_contract import ObjectName as ClientSecond
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.export_brep import export_brep_operation


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


complete: ExportBrepCollaborators = CompleteDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> ExportBrepCollaborators:
    return collaborators


missing_postcondition: ExportBrepCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]


_ = ExportBrepRequest
incomplete_success: ExportBrepSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    name = ClientSecond("Box")
    assert_type(client.export_brep(document, name, "/tmp/out.brep"), object)
    assert_type(export_brep_operation(client, "Doc", "Box", "/tmp/out.brep"), CallToolResult)
    client.export_brep(name, document, "/tmp/out.brep")  # type: ignore[arg-type]
    client.export_brep("Doc", "Box", "/tmp/out.brep")  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: MutationReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    body = document.getObject("Body")
    if body is not None:
        body.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
