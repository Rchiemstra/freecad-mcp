"""Static contract examples for the relink_references collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.relink_references_contract import (
    RelinkReferencesRequest,
    RelinkReferencesSuccess,
    RelinkReferencesDocument,
    RelinkReferencesName,
    RelinkReferencesReadDocument,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.relink_references import (
    RelinkReferencesCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.relink_references import relink_references_operation


class CompleteRelinkReferencesDouble:
    """A test double that satisfies every dependency."""

    def validate_document_invariants(self, document: RelinkReferencesReadDocument) -> object:
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

    def validate_document_invariants(self, document: RelinkReferencesReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


complete: RelinkReferencesCollaborators = CompleteRelinkReferencesDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> RelinkReferencesCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


missing_postcondition: RelinkReferencesCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
valid_request = RelinkReferencesRequest(doc_name=document_name, from_obj="Value", to_obj="Value")


def public_client_preserves_names(client: FreeCADConnection) -> None:
    assert_type(relink_references_operation(client, True, "Doc", "Value", "Value"), CallToolResult)


def postcondition_surface_is_read_only(document: RelinkReferencesReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    item = document.getObject("Body")
    if item is not None:
        item.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
