"""Static contract examples for the rotate collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.rotate_contract import (
    RotateRequest,
    RotateSuccess,
    MutationReadDocument,
    DocumentName,
    ObjectName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.rotate import (
    RotateCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.rotate_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp._shared.protocol.rotate_contract import ObjectName as ClientSecond
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.rotate import rotate_operation


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


complete: RotateCollaborators = CompleteDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> RotateCollaborators:
    return collaborators


missing_postcondition: RotateCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]


_ = RotateRequest
incomplete_success: RotateSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    name = ClientSecond("Box")
    assert_type(client.rotate(document, name, 0, 0, 1, 90.0), object)
    assert_type(rotate_operation(client, True, "Doc", "Box", 0, 0, 1, 90.0), CallToolResult)
    client.rotate(name, document, 0, 0, 1, 90.0)  # type: ignore[arg-type]
    client.rotate("Doc", "Box", 0, 0, 1, 90.0)  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: MutationReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    body = document.getObject("Body")
    if body is not None:
        body.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
