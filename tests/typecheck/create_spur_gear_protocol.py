"""Static contract examples for the create_spur_gear collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.create_spur_gear_contract import (
    CreateSpurGearRequest,
    CreateSpurGearSuccess,
    MutationReadDocument,
    DocumentName,
    GearName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.create_spur_gear import (
    CreateSpurGearCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.create_spur_gear_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp._shared.protocol.create_spur_gear_contract import GearName as ClientSecond
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.create_spur_gear import create_spur_gear_operation


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


complete: CreateSpurGearCollaborators = CompleteDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> CreateSpurGearCollaborators:
    return collaborators


missing_postcondition: CreateSpurGearCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]


_ = CreateSpurGearRequest
incomplete_success: CreateSpurGearSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    name = ClientSecond("Gear")
    assert_type(client.create_spur_gear(document, name, 8, 2.0, 10.0), object)
    assert_type(create_spur_gear_operation(client, True, "Doc", "Gear", 8, 2.0, 10.0), CallToolResult)
    client.create_spur_gear(name, document, 8, 2.0, 10.0)  # type: ignore[arg-type]
    client.create_spur_gear("Doc", "Gear", 8, 2.0, 10.0)  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: MutationReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    body = document.getObject("Body")
    if body is not None:
        body.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
