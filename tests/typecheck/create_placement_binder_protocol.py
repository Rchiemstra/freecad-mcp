"""Static contract examples for the create_placement_binder collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.create_placement_binder_contract import (
    CreatePlacementBinderRequest,
    CreatePlacementBinderSuccess,
    CreatePlacementBinderDocument,
    CreatePlacementBinderName,
    CreatePlacementBinderReadDocument,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.create_placement_binder import (
    CreatePlacementBinderCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.create_placement_binder import create_placement_binder_operation


class CompleteCreatePlacementBinderDouble:
    """A test double that satisfies every dependency."""

    def validate_document_invariants(self, document: CreatePlacementBinderReadDocument) -> object:
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

    def validate_document_invariants(self, document: CreatePlacementBinderReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


complete: CreatePlacementBinderCollaborators = CompleteCreatePlacementBinderDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> CreatePlacementBinderCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


missing_postcondition: CreatePlacementBinderCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
valid_request = CreatePlacementBinderRequest(doc_name=document_name, owner_body="Value", name="Value", source="Value", relative=True, bind_mode="Value")


def public_client_preserves_names(client: FreeCADConnection) -> None:
    assert_type(create_placement_binder_operation(client, True, "Doc", "Value", "Value", "Value", True, "Value"), CallToolResult)


def postcondition_surface_is_read_only(document: CreatePlacementBinderReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    item = document.getObject("Body")
    if item is not None:
        item.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
