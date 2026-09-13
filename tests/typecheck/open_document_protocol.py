"""Static contract examples for the open_document collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.open_document_contract import (
    PathName,
    OpenDocumentCollaborators,
    OpenDocumentReadDocument,
    OpenDocumentRequest,
    OpenDocumentSuccess,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.open_document import (
    OpenDocumentCollaborators as LeafCollaborators,
)
from freecad_mcp._shared.protocol.open_document_contract import (
    PathName as ClientPathName,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.open_document import open_document_operation


class CompleteDouble:
    def validate_document_invariants(self, document: OpenDocumentReadDocument) -> object:
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
    def validate_document_invariants(self, document: OpenDocumentReadDocument) -> object:
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
path_name = PathName('C:/models/part.FCStd')
valid_request = OpenDocumentRequest(path=path_name)
incomplete_success: OpenDocumentSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    path = ClientPathName("C:/models/part.FCStd")
    assert_type(client.open_document(path), object)
    assert_type(open_document_operation(client, "C:/models/part.FCStd"), CallToolResult)
    client.open_document(123)  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: OpenDocumentReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]


__all__: list[str] = []
