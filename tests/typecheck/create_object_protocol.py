"""Static contract examples for the create_object collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.create_object_contract import (
    ObjectName, ObjectType,
    CreateObjectCollaborators,
    CreateObjectReadDocument,
    CreateObjectRequest,
    CreateObjectSuccess,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.create_object import (
    CreateObjectCollaborators as LeafCollaborators,
)
from freecad_mcp._shared.protocol.create_object_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.create_object import create_object_operation


class CompleteDouble:
    def validate_document_invariants(self, document: CreateObjectReadDocument) -> object:
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
    def validate_document_invariants(self, document: CreateObjectReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
    ) -> object:
        return None


complete: LeafCollaborators = CompleteDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> LeafCollaborators:
    return collaborators


missing_postcondition: LeafCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
valid_request = CreateObjectRequest(doc_name=document_name, object_name=ObjectName('Box'), object_type=ObjectType('Part::Box'), properties=(), analysis_name=None)
incomplete_success: CreateObjectSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    assert_type(client.create_object(document, {'Name': 'Box', 'Type': 'Part::Box'}), object)
    assert_type(create_object_operation(client, True, "Doc", "Part::Box", "Box"), CallToolResult)
    client.create_object(123, 123)  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: CreateObjectReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]


__all__: list[str] = []
