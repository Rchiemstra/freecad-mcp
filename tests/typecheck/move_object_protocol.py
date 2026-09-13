"""Static contract examples for the move_object collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.move_object_contract import (
    MoveObjectRequest,
    MoveObjectSuccess,
    MoveObjectDocument,
    MoveObjectName,
    MoveObjectReadDocument,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.move_object import (
    MoveObjectCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.move_object import move_object_operation


class CompleteMoveObjectDouble:
    """A test double that satisfies every dependency."""

    def validate_document_invariants(self, document: MoveObjectReadDocument) -> object:
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

    def validate_document_invariants(self, document: MoveObjectReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


complete: MoveObjectCollaborators = CompleteMoveObjectDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> MoveObjectCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


missing_postcondition: MoveObjectCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
valid_request = MoveObjectRequest(doc_name=document_name, obj_name="Value", target_container="Value", remove_from_old_parent=True)


def public_client_preserves_names(client: FreeCADConnection) -> None:
    assert_type(move_object_operation(client, True, "Doc", "Value", "Value", True), CallToolResult)


def postcondition_surface_is_read_only(document: MoveObjectReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    item = document.getObject("Body")
    if item is not None:
        item.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
