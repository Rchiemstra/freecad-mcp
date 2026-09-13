"""Static contract examples for the set_expression collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.set_expression_contract import (
    SetExpressionRequest,
    SetExpressionSuccess,
    SetExpressionDocument,
    SetExpressionName,
    SetExpressionReadDocument,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.set_expression import (
    SetExpressionCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.set_expression import set_expression_operation


class CompleteSetExpressionDouble:
    """A test double that satisfies every dependency."""

    def validate_document_invariants(self, document: SetExpressionReadDocument) -> object:
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

    def validate_document_invariants(self, document: SetExpressionReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


complete: SetExpressionCollaborators = CompleteSetExpressionDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> SetExpressionCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


missing_postcondition: SetExpressionCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
valid_request = SetExpressionRequest(doc_name=document_name, object_name="Value", prop_path="Value", expression="Value")


def public_client_preserves_names(client: FreeCADConnection) -> None:
    assert_type(set_expression_operation(client, True, "Doc", "Value", "Value", "Value"), CallToolResult)


def postcondition_surface_is_read_only(document: SetExpressionReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    item = document.getObject("Body")
    if item is not None:
        item.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
