"""Static contract examples for the recompute_document collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.recompute_document_contract import (
    RecomputeDocumentCollaborators,
    RecomputeDocumentReadDocument,
    RecomputeDocumentRequest,
    RecomputeDocumentSuccess,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.recompute_document import (
    RecomputeDocumentCollaborators as LeafCollaborators,
)
from freecad_mcp._shared.protocol.recompute_document_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.recompute_document import recompute_document_operation


class CompleteDouble:
    def validate_document_invariants(self, document: RecomputeDocumentReadDocument) -> object:
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
    def validate_document_invariants(self, document: RecomputeDocumentReadDocument) -> object:
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
valid_request = RecomputeDocumentRequest(doc_name=document_name)
incomplete_success: RecomputeDocumentSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    assert_type(client.recompute_document(document), object)
    assert_type(recompute_document_operation(client, "Doc"), CallToolResult)
    client.recompute_document(123)  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: RecomputeDocumentReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]


__all__: list[str] = []
