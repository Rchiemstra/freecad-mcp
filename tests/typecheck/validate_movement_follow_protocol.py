"""Static contract examples for the validate_movement_follow collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.validate_movement_follow_contract import (
    ValidateMovementFollowRequest,
    ValidateMovementFollowSuccess,
    ValidateMovementFollowDocument,
    ValidateMovementFollowName,
    ValidateMovementFollowReadDocument,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.validate_movement_follow import (
    ValidateMovementFollowCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.validate_movement_follow import validate_movement_follow_operation


class CompleteValidateMovementFollowDouble:
    """A test double that satisfies every dependency."""

    def validate_document_invariants(self, document: ValidateMovementFollowReadDocument) -> object:
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

    def validate_document_invariants(self, document: ValidateMovementFollowReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


complete: ValidateMovementFollowCollaborators = CompleteValidateMovementFollowDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> ValidateMovementFollowCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


missing_postcondition: ValidateMovementFollowCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
valid_request = ValidateMovementFollowRequest(doc_name=document_name, source="Value", dependents=["Seed"], translation=[0.0, 0.0, 1.0], axis=[0.0, 0.0, 1.0], angle_deg=1.0, restore=True, tolerance=1e-07)


def public_client_preserves_names(client: FreeCADConnection) -> None:
    assert_type(validate_movement_follow_operation(client, True, "Doc", "Value", ["Seed"], [0, 0, 1], [0, 0, 1], 1.0, True, 1e-07), CallToolResult)


def postcondition_surface_is_read_only(document: ValidateMovementFollowReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    item = document.getObject("Body")
    if item is not None:
        item.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
