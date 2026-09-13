"""Static contract examples for the edit_object collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.edit_object_contract import (
    ObjectName,
    EditObjectCollaborators,
    EditObjectReadDocument,
    EditObjectRequest,
    EditObjectSuccess,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.edit_object import (
    EditObjectCollaborators as LeafCollaborators,
)
from freecad_mcp._shared.protocol.edit_object_contract import (
    DocumentName as ClientDocumentName,
    ObjectName as ClientObjectName,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.edit_object import edit_object_operation


class CompleteDouble:
    def validate_document_invariants(self, document: EditObjectReadDocument) -> object:
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
    def validate_document_invariants(self, document: EditObjectReadDocument) -> object:
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
valid_request = EditObjectRequest(doc_name=document_name, object_name=ObjectName('Box'), properties=())
incomplete_success: EditObjectSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    assert_type(client.edit_object(document, ClientObjectName('Box'), {'Properties': {'Label': 'Box'}}), object)
    assert_type(edit_object_operation(client, True, "Doc", "Box", {"Label": "Box"}), CallToolResult)
    client.edit_object(123, 123, 123)  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: EditObjectReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]


__all__: list[str] = []
