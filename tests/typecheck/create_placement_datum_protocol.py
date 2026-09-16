"""Static contract examples for the create_placement_datum collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.create_placement_datum_contract import (
    CreatePlacementDatumRequest,
    CreatePlacementDatumSuccess,
    CreatePlacementDatumDocument,
    CreatePlacementDatumName,
    CreatePlacementDatumReadDocument,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.create_placement_datum import (
    CreatePlacementDatumCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.create_placement_datum import create_placement_datum_operation


class CompleteCreatePlacementDatumDouble:
    """A test double that satisfies every dependency."""

    def validate_document_invariants(self, document: CreatePlacementDatumReadDocument) -> object:
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

    def validate_document_invariants(self, document: CreatePlacementDatumReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


complete: CreatePlacementDatumCollaborators = CompleteCreatePlacementDatumDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> CreatePlacementDatumCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


missing_postcondition: CreatePlacementDatumCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
valid_request = CreatePlacementDatumRequest(doc_name=document_name, owner_body="Value", name="Value", source="Value", relative=True, offset=None)


def public_client_preserves_names(client: FreeCADConnection) -> None:
    assert_type(create_placement_datum_operation(client, True, "Doc", "Value", "Value", "Value", True, None), CallToolResult)


def postcondition_surface_is_read_only(document: CreatePlacementDatumReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    item = document.getObject("Body")
    if item is not None:
        item.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
